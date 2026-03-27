"""Tests for GradioRenderer and _envelope_to_chat_messages."""
from __future__ import annotations

import pytest

from tests.conftest import make_envelope
from ofp_playground.renderer.gradio_ui import (
    GradioRenderer,
    _envelope_to_chat_messages,
    _agent_icon,
    _agent_color,
    _floor_event_message,
)


# ---------------------------------------------------------------------------
# _agent_icon
# ---------------------------------------------------------------------------

class TestAgentIcon:
    def test_image_uri_gets_palette_icon(self):
        icon = _agent_icon("tag:test:image-painter")
        assert icon == "🎨"

    def test_video_uri_gets_icon(self):
        icon = _agent_icon("tag:test:video-bot")
        assert icon == "🎬"

    def test_unknown_uri_gets_default(self):
        icon = _agent_icon("tag:test:mystery-agent")
        assert icon == "💬"

    def test_music_uri_gets_icon(self):
        assert _agent_icon("tag:test:music-composer") == "🎵"

    def test_web_uri_gets_icon(self):
        assert _agent_icon("tag:test:web-scraper") == "🌐"

    def test_human_uri_gets_icon(self):
        assert _agent_icon("tag:test:human-user") == "👤"


# ---------------------------------------------------------------------------
# _agent_color
# ---------------------------------------------------------------------------

class TestAgentColor:
    def test_returns_hex_color(self):
        color_map: dict = {}
        color = _agent_color("tag:test:agent-1", color_map)
        assert color.startswith("#")

    def test_same_uri_same_color(self):
        color_map: dict = {}
        c1 = _agent_color("tag:test:agent-1", color_map)
        c2 = _agent_color("tag:test:agent-1", color_map)
        assert c1 == c2

    def test_different_uris_may_differ(self):
        color_map: dict = {}
        c1 = _agent_color("tag:test:agent-1", color_map)
        c2 = _agent_color("tag:test:agent-2", color_map)
        # Not guaranteed to differ but map should have two entries
        assert len(color_map) == 2

    def test_rotation_uses_palette(self):
        from ofp_playground.renderer.gradio_ui import _AGENT_COLORS
        color_map: dict = {}
        colors_assigned = set()
        for i in range(len(_AGENT_COLORS) + 2):
            c = _agent_color(f"tag:test:agent-{i}", color_map)
            colors_assigned.add(c)
        # Should rotate through the palette
        assert len(colors_assigned) == len(_AGENT_COLORS)


# ---------------------------------------------------------------------------
# _floor_event_message
# ---------------------------------------------------------------------------

class TestFloorEventMessage:
    def test_role_is_system(self):
        msg = _floor_event_message("Floor granted to Alice")
        assert msg["role"] == "system"

    def test_content_in_message(self):
        msg = _floor_event_message("Agent Bob joined")
        assert "Agent Bob joined" in msg["content"]

    def test_has_metadata(self):
        msg = _floor_event_message("x")
        assert "metadata" in msg


# ---------------------------------------------------------------------------
# _envelope_to_chat_messages — text-only
# ---------------------------------------------------------------------------

class TestEnvelopeToMessages:
    def _names(self):
        return {"tag:test:agent": "TestAgent"}

    def test_text_only_returns_one_message(self):
        env = make_envelope("tag:test:agent", "Hello there")
        msgs = _envelope_to_chat_messages(env, self._names(), set(), {})
        assert len(msgs) == 1

    def test_text_content_clean(self):
        """Message content should NOT contain '**Name**:' prefix."""
        env = make_envelope("tag:test:agent", "Hello there")
        msgs = _envelope_to_chat_messages(env, self._names(), set(), {})
        assert msgs[0]["content"] == "Hello there"

    def test_sender_name_in_metadata_title(self):
        env = make_envelope("tag:test:agent", "Hello")
        msgs = _envelope_to_chat_messages(env, self._names(), set(), {})
        title = msgs[0]["metadata"]["title"]
        assert "TestAgent" in title

    def test_agent_role_is_assistant(self):
        env = make_envelope("tag:test:agent", "Hello")
        msgs = _envelope_to_chat_messages(env, self._names(), set(), {})
        assert msgs[0]["role"] == "assistant"

    def test_human_role_is_user(self):
        env = make_envelope("tag:test:human", "Hello")
        msgs = _envelope_to_chat_messages(env, {}, {"tag:test:human"}, {})
        assert msgs[0]["role"] == "user"

    def test_non_utterance_event_returns_empty(self):
        from openfloor import Envelope, Sender, Conversation
        env = Envelope(
            sender=Sender(speakerUri="tag:test:a", serviceUrl="local://test"),
            conversation=Conversation(id="conv:1"),
            events=[],
        )
        msgs = _envelope_to_chat_messages(env, {}, set(), {})
        assert msgs == []

    def test_unknown_sender_uses_uri_suffix(self):
        env = make_envelope("tag:test:mystery-bot", "Hello")
        msgs = _envelope_to_chat_messages(env, {}, set(), {})
        assert len(msgs) == 1
        # URI suffix used as fallback name
        title = msgs[0]["metadata"]["title"]
        assert "mystery-bot" in title


# ---------------------------------------------------------------------------
# _envelope_to_chat_messages — media
# ---------------------------------------------------------------------------

class TestMediaMessages:
    def test_image_envelope_emits_two_messages(self, tmp_path):
        """Text message + image component message."""
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n")
        env = make_envelope("tag:test:painter", "A sunset", media_key="image", media_path=str(img))
        msgs = _envelope_to_chat_messages(env, {"tag:test:painter": "Painter"}, set(), {})
        assert len(msgs) == 2
        # First is text, second is image component

    def test_missing_media_file_no_image_component(self):
        """If media path doesn't exist, media component is not added (unless no text)."""
        env = make_envelope(
            "tag:test:painter", "A sunset",
            media_key="image", media_path="/nonexistent/img.png"
        )
        msgs = _envelope_to_chat_messages(env, {"tag:test:painter": "Painter"}, set(), {})
        # Text message still present, no image component
        assert any(m["content"] == "A sunset" for m in msgs)
        # No gr.Image component
        import gradio as gr
        assert not any(isinstance(m.get("content"), gr.Image) for m in msgs)


# ---------------------------------------------------------------------------
# GradioRenderer
# ---------------------------------------------------------------------------

class TestGradioRenderer:
    def _renderer(self, names=None, humans=None):
        return GradioRenderer(
            agent_names=names or {"tag:test:agent": "TestAgent"},
            human_uris=humans or set(),
        )

    def test_ingest_text_envelope_returns_true(self):
        r = self._renderer()
        env = make_envelope("tag:test:agent", "Hello")
        assert r.ingest_envelope(env) is True

    def test_ingest_non_utterance_returns_false(self):
        from openfloor import Envelope, Sender, Conversation
        r = self._renderer()
        env = Envelope(
            sender=Sender(speakerUri="tag:test:a", serviceUrl="local://test"),
            conversation=Conversation(id="conv:1"),
            events=[],
        )
        assert r.ingest_envelope(env) is False

    def test_get_history_returns_copy(self):
        r = self._renderer()
        r.ingest_envelope(make_envelope("tag:test:agent", "Hello"))
        h1 = r.get_history()
        h1.clear()
        h2 = r.get_history()
        assert len(h2) >= 1

    def test_history_grows_on_ingestion(self):
        r = self._renderer()
        for i in range(3):
            r.ingest_envelope(make_envelope("tag:test:agent", f"msg {i}"))
        assert len(r.get_history()) == 3

    def test_add_agent_updates_names(self):
        r = self._renderer(names={})
        r.add_agent("tag:test:new-agent", "NewAgent")
        env = make_envelope("tag:test:new-agent", "Hello")
        r.ingest_envelope(env)
        title = r.get_history()[0]["metadata"]["title"]
        assert "NewAgent" in title

    def test_add_human_marks_as_user(self):
        r = self._renderer(names={}, humans=set())
        r.add_human("tag:test:human-1")
        env = make_envelope("tag:test:human-1", "Hi!")
        r.ingest_envelope(env)
        assert r.get_history()[0]["role"] == "user"

    def test_add_system_event_appended(self):
        r = self._renderer()
        r.add_system_event("Floor granted to Alice")
        h = r.get_history()
        assert any("Floor granted" in m["content"] for m in h)
        assert any(m["role"] == "system" for m in h)
