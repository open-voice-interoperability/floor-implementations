"""Tests for WebHumanAgent — queue creation, send_text, queue integration."""
from __future__ import annotations

import asyncio
import pytest

from ofp_playground.agents.web_human import WebHumanAgent
from ofp_playground.bus.message_bus import MessageBus, FLOOR_MANAGER_URI


def _make_agent(name="User"):
    return WebHumanAgent(
        name=name,
        bus=MessageBus(),
        conversation_id="conv:test",
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestInit:
    def test_speaker_uri_contains_name(self):
        agent = _make_agent("Alice")
        assert "human-alice" in agent.speaker_uri

    def test_input_queue_created(self):
        agent = _make_agent()
        assert isinstance(agent.input_queue, asyncio.Queue)

    def test_output_queue_created(self):
        agent = _make_agent()
        assert isinstance(agent.output_queue, asyncio.Queue)

    def test_name_property(self):
        agent = _make_agent("Carol")
        assert agent.name == "Carol"

    def test_spaces_in_name_normalised(self):
        agent = _make_agent("John Doe")
        assert "john-doe" in agent.speaker_uri


# ---------------------------------------------------------------------------
# send_text — creates and sends an envelope
# ---------------------------------------------------------------------------

class TestSendText:
    @pytest.mark.asyncio
    async def test_send_text_goes_to_bus(self):
        bus = MessageBus()
        fm_q: asyncio.Queue = asyncio.Queue()
        await bus.register(FLOOR_MANAGER_URI, fm_q)

        agent = WebHumanAgent(name="User", bus=bus, conversation_id="conv:1")
        await bus.register(agent.speaker_uri, agent.queue)
        await agent.send_text("Hello from web UI")

        # Floor manager should receive the envelope
        assert not fm_q.empty()
        env = fm_q.get_nowait()
        assert env.sender.speakerUri == agent.speaker_uri

    @pytest.mark.asyncio
    async def test_send_text_envelope_contains_text(self):
        bus = MessageBus()
        fm_q: asyncio.Queue = asyncio.Queue()
        await bus.register(FLOOR_MANAGER_URI, fm_q)

        agent = WebHumanAgent(name="User", bus=bus, conversation_id="conv:1")
        await bus.register(agent.speaker_uri, agent.queue)
        await agent.send_text("Test message content")

        env = fm_q.get_nowait()
        event = env.events[0]
        de = event.dialogEvent
        text = " ".join(t.value for t in de.features["text"].tokens if t.value)
        assert text == "Test message content"


# ---------------------------------------------------------------------------
# Queue integration — bus → output_queue forwarding
# ---------------------------------------------------------------------------

class TestQueueForwarding:
    @pytest.mark.asyncio
    async def test_run_forwards_bus_to_output_queue(self):
        """Messages arriving on the bus are forwarded to WebHumanAgent.output_queue."""
        bus = MessageBus()
        fm_q: asyncio.Queue = asyncio.Queue()
        await bus.register(FLOOR_MANAGER_URI, fm_q)

        agent = WebHumanAgent(name="User", bus=bus, conversation_id="conv:1")

        # Start agent in background
        task = asyncio.create_task(agent.run())
        await asyncio.sleep(0.1)  # let it register and start

        # Send a test envelope into the bus (from another agent)
        from openfloor import Conversation, Envelope, Sender, UtteranceEvent, DialogEvent, TextFeature, Token
        env = Envelope(
            sender=Sender(speakerUri="tag:test:other-agent", serviceUrl="local://test"),
            conversation=Conversation(id="conv:1"),
            events=[UtteranceEvent(dialogEvent=DialogEvent(
                id="test-1",
                speakerUri="tag:test:other-agent",
                features={"text": TextFeature(mimeType="text/plain", tokens=[Token(value="Hi there")])}
            ))],
        )
        await bus.send(env)
        await asyncio.sleep(0.15)  # let run() process

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # The envelope should have been forwarded to output_queue
        assert not agent.output_queue.empty()
        received = agent.output_queue.get_nowait()
        assert received.sender.speakerUri == "tag:test:other-agent"

    @pytest.mark.asyncio
    async def test_input_queue_drives_send(self):
        """Text placed in input_queue is sent into the bus as an utterance."""
        bus = MessageBus()
        fm_q: asyncio.Queue = asyncio.Queue()
        await bus.register(FLOOR_MANAGER_URI, fm_q)

        agent = WebHumanAgent(name="User", bus=bus, conversation_id="conv:1")
        task = asyncio.create_task(agent.run())
        await asyncio.sleep(0.1)

        await agent.input_queue.put("Hello from the UI")
        await asyncio.sleep(0.2)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Floor manager should have received the utterance
        found = False
        while not fm_q.empty():
            env = fm_q.get_nowait()
            for event in (env.events or []):
                de = getattr(event, "dialogEvent", None)
                if de and de.features.get("text"):
                    tokens = de.features["text"].tokens
                    if any(t.value == "Hello from the UI" for t in tokens if t.value):
                        found = True
        assert found
