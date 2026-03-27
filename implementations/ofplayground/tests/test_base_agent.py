"""Tests for BasePlaygroundAgent — envelope builders, floor anti-dup, retry logic."""
from __future__ import annotations

import asyncio
import pytest

from openfloor import Envelope, Conversation, Sender, TextFeature, Token, UtteranceEvent, DialogEvent

from ofp_playground.agents.base import BasePlaygroundAgent
from ofp_playground.bus.message_bus import MessageBus
from tests.conftest import ConcreteAgent, make_envelope


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestInit:
    def test_speaker_uri_property(self):
        bus = MessageBus()
        a = ConcreteAgent("tag:test:a", "TestA", "local://test", bus, "conv:1")
        assert a.speaker_uri == "tag:test:a"

    def test_name_property(self):
        bus = MessageBus()
        a = ConcreteAgent("tag:test:a", "TestA", "local://test", bus, "conv:1")
        assert a.name == "TestA"

    def test_queue_is_asyncio_queue(self):
        bus = MessageBus()
        a = ConcreteAgent("tag:test:a", "TestA", "local://test", bus, "conv:1")
        assert isinstance(a.queue, asyncio.Queue)

    def test_pending_floor_request_starts_false(self):
        bus = MessageBus()
        a = ConcreteAgent("tag:test:a", "TestA", "local://test", bus, "conv:1")
        assert a._pending_floor_request is False

    def test_stop_sets_running_false(self):
        bus = MessageBus()
        a = ConcreteAgent("tag:test:a", "TestA", "local://test", bus, "conv:1")
        a._running = True
        a.stop()
        assert a._running is False


# ---------------------------------------------------------------------------
# _make_sender / _make_conversation
# ---------------------------------------------------------------------------

class TestMakeHelpers:
    def _agent(self):
        return ConcreteAgent("tag:test:a", "A", "local://svc", MessageBus(), "conv:xyz")

    def test_make_sender_uri(self):
        sender = self._agent()._make_sender()
        assert sender.speakerUri == "tag:test:a"

    def test_make_sender_service_url(self):
        sender = self._agent()._make_sender()
        assert sender.serviceUrl == "local://svc"

    def test_make_conversation_id(self):
        conv = self._agent()._make_conversation()
        assert conv.id == "conv:xyz"


# ---------------------------------------------------------------------------
# _make_utterance_envelope
# ---------------------------------------------------------------------------

class TestMakeUtteranceEnvelope:
    def _agent(self):
        return ConcreteAgent("tag:test:alice", "Alice", "local://test", MessageBus(), "conv:1")

    def test_returns_envelope(self):
        env = self._agent()._make_utterance_envelope("Hello!")
        assert isinstance(env, Envelope)

    def test_sender_uri_correct(self):
        env = self._agent()._make_utterance_envelope("Hello!")
        assert env.sender.speakerUri == "tag:test:alice"

    def test_single_utterance_event(self):
        env = self._agent()._make_utterance_envelope("Hello!")
        assert len(env.events) == 1

    def test_text_content(self):
        env = self._agent()._make_utterance_envelope("hi there")
        de = env.events[0].dialogEvent
        text_tokens = de.features["text"].tokens
        assert any(t.value == "hi there" for t in text_tokens)

    def test_conversation_id_set(self):
        env = self._agent()._make_utterance_envelope("Hello!")
        assert env.conversation.id == "conv:1"


# ---------------------------------------------------------------------------
# _make_media_utterance_envelope
# ---------------------------------------------------------------------------

class TestMakeMediaUtteranceEnvelope:
    def _agent(self):
        return ConcreteAgent("tag:test:a", "A", "local://test", MessageBus(), "conv:1")

    def test_has_text_and_media_features(self):
        env = self._agent()._make_media_utterance_envelope(
            "A beautiful image", "image", "image/png", "/tmp/img.png"
        )
        de = env.events[0].dialogEvent
        assert "text" in de.features
        assert "image" in de.features

    def test_media_path_in_token(self):
        env = self._agent()._make_media_utterance_envelope(
            "desc", "video", "video/mp4", "/tmp/vid.mp4"
        )
        de = env.events[0].dialogEvent
        token_val = de.features["video"].tokens[0].value
        assert token_val == "/tmp/vid.mp4"

    def test_text_value_preserved(self):
        env = self._agent()._make_media_utterance_envelope(
            "My description", "image", "image/png", "/img.png"
        )
        de = env.events[0].dialogEvent
        text_val = de.features["text"].tokens[0].value
        assert text_val == "My description"


# ---------------------------------------------------------------------------
# _extract_text_from_envelope
# ---------------------------------------------------------------------------

class TestExtractText:
    def _agent(self):
        return ConcreteAgent("tag:test:a", "A", "local://test", MessageBus(), "conv:1")

    def test_extracts_text_from_utterance(self):
        env = make_envelope("tag:test:sender", "Hello world")
        text = self._agent()._extract_text_from_envelope(env)
        assert text == "Hello world"

    def test_returns_none_for_no_utterance_event(self):
        env = Envelope(
            sender=Sender(speakerUri="tag:test:a", serviceUrl="local://test"),
            conversation=Conversation(id="conv:1"),
            events=[],
        )
        assert self._agent()._extract_text_from_envelope(env) is None

    def test_returns_none_for_empty_tokens(self):
        env = make_envelope("tag:test:a", "")  # empty text
        # When text is empty, tokens either have empty value or no tokens at all
        result = self._agent()._extract_text_from_envelope(env)
        # Either None or empty string acceptable (join of empty tokens)
        assert result == "" or result is None

    def test_multiword_text_joined(self):
        """Tokens are joined with spaces into a single string."""
        env = make_envelope("tag:test:a", "Hello there friend")
        text = self._agent()._extract_text_from_envelope(env)
        assert text == "Hello there friend"


# ---------------------------------------------------------------------------
# _get_sender_uri
# ---------------------------------------------------------------------------

class TestGetSenderUri:
    def _agent(self):
        return ConcreteAgent("tag:test:a", "A", "local://test", MessageBus(), "conv:1")

    def test_returns_sender_uri(self):
        env = make_envelope("tag:test:sender")
        assert self._agent()._get_sender_uri(env) == "tag:test:sender"

    def test_returns_unknown_for_no_sender(self):
        env = Envelope(
            sender=None,
            conversation=Conversation(id="conv:1"),
            events=[],
        )
        assert self._agent()._get_sender_uri(env) == "unknown"


# ---------------------------------------------------------------------------
# _is_retryable_error
# ---------------------------------------------------------------------------

class TestIsRetryableError:
    def test_429_is_retryable(self):
        assert BasePlaygroundAgent._is_retryable_error("Error 429 rate limit exceeded")

    def test_rate_is_retryable(self):
        assert BasePlaygroundAgent._is_retryable_error("RateLimitError: too many requests")

    def test_quota_is_retryable(self):
        assert BasePlaygroundAgent._is_retryable_error("quota exceeded")

    def test_resource_exhausted_is_retryable(self):
        assert BasePlaygroundAgent._is_retryable_error("RESOURCE_EXHAUSTED")

    def test_503_is_retryable(self):
        assert BasePlaygroundAgent._is_retryable_error("503 Service Unavailable")

    def test_overload_is_retryable(self):
        assert BasePlaygroundAgent._is_retryable_error("overloaded, please retry")

    def test_timeout_is_retryable(self):
        assert BasePlaygroundAgent._is_retryable_error("timeout occurred")

    def test_401_not_retryable(self):
        assert not BasePlaygroundAgent._is_retryable_error("401 Unauthorized")

    def test_404_not_retryable(self):
        assert not BasePlaygroundAgent._is_retryable_error("404 Not Found")

    def test_auth_not_retryable(self):
        assert not BasePlaygroundAgent._is_retryable_error("invalid_api_key authentication failed")

    def test_generic_error_not_retryable(self):
        assert not BasePlaygroundAgent._is_retryable_error("Something went wrong")


# ---------------------------------------------------------------------------
# _call_with_retry
# ---------------------------------------------------------------------------

class TestCallWithRetry:
    def _agent(self, timeout=None, max_retries=0):
        bus = MessageBus()
        a = ConcreteAgent("tag:test:a", "A", "local://test", bus, "conv:1")
        a._timeout = timeout
        a._max_retries = max_retries
        return a

    @pytest.mark.asyncio
    async def test_success_returns_value(self):
        agent = self._agent()

        async def _coro():
            return 42

        result = await agent._call_with_retry(lambda: _coro())
        assert result == 42

    @pytest.mark.asyncio
    async def test_success_no_retry_needed(self):
        agent = self._agent()
        call_count = 0

        async def coro():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await agent._call_with_retry(lambda: coro())
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_non_retryable_raises_immediately(self):
        agent = self._agent(max_retries=2)

        async def coro():
            raise ValueError("401 Unauthorized")

        with pytest.raises(ValueError, match="401"):
            await agent._call_with_retry(lambda: coro())

    @pytest.mark.asyncio
    async def test_retryable_error_retries(self):
        agent = self._agent(max_retries=2)
        agent._retry_delay = 0.0  # instant retries in tests
        call_count = 0

        async def coro():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("429 rate limit")
            return "success"

        result = await agent._call_with_retry(lambda: coro())
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exhausted_retries_raises_last(self):
        agent = self._agent(max_retries=1)
        agent._retry_delay = 0.0

        async def coro():
            raise Exception("503 overload")

        with pytest.raises(Exception, match="503"):
            await agent._call_with_retry(lambda: coro())

    @pytest.mark.asyncio
    async def test_timeout_raises_after_limit(self):
        agent = self._agent(timeout=0.05)

        async def slow_coro():
            await asyncio.sleep(10)
            return "should not reach"

        with pytest.raises(asyncio.TimeoutError):
            await agent._call_with_retry(lambda: slow_coro())


# ---------------------------------------------------------------------------
# request_floor / yield_floor anti-duplicate
# ---------------------------------------------------------------------------

class TestFloorAntiDuplicate:
    @pytest.mark.asyncio
    async def test_request_floor_sets_pending(self):
        bus = MessageBus()
        fm_q: asyncio.Queue = asyncio.Queue()
        await bus.register("tag:ofp-playground.local,2025:floor-manager", fm_q)
        agent = ConcreteAgent("tag:test:a", "A", "local://test", bus, "conv:1")
        await bus.register(agent.speaker_uri, agent.queue)
        await agent.request_floor("reason")
        assert agent._pending_floor_request is True

    @pytest.mark.asyncio
    async def test_duplicate_request_not_sent(self):
        bus = MessageBus()
        fm_q: asyncio.Queue = asyncio.Queue()
        await bus.register("tag:ofp-playground.local,2025:floor-manager", fm_q)
        agent = ConcreteAgent("tag:test:a", "A", "local://test", bus, "conv:1")
        await bus.register(agent.speaker_uri, agent.queue)

        await agent.request_floor("first")
        await agent.request_floor("second")  # should be noop
        # Only one RequestFloorEvent should reach the floor manager
        got = []
        while not fm_q.empty():
            got.append(fm_q.get_nowait())
        assert len(got) == 1

    @pytest.mark.asyncio
    async def test_yield_floor_clears_pending(self):
        bus = MessageBus()
        fm_q: asyncio.Queue = asyncio.Queue()
        await bus.register("tag:ofp-playground.local,2025:floor-manager", fm_q)
        agent = ConcreteAgent("tag:test:a", "A", "local://test", bus, "conv:1")
        await bus.register(agent.speaker_uri, agent.queue)
        await agent.request_floor("reason")
        await agent.yield_floor()
        assert agent._pending_floor_request is False
