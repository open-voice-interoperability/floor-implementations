"""Tests for ConversationHistory — buffer management and formatting."""
from __future__ import annotations

import pytest

from ofp_playground.floor.history import ConversationHistory
from ofp_playground.models.artifact import ArtifactFeature, Utterance


def _text_utt(name: str, text: str, uri: str = "tag:test:agent") -> Utterance:
    return Utterance.from_text(uri, name, text)


def _image_utt(name: str, desc: str, path: str) -> Utterance:
    return Utterance.from_image(f"tag:test:{name.lower()}", name, desc, path)


# ---------------------------------------------------------------------------
# add / overflow
# ---------------------------------------------------------------------------

class TestAdd:
    def test_add_single_entry(self):
        h = ConversationHistory()
        h.add(_text_utt("Alice", "Hello"))
        assert len(h) == 1

    def test_add_multiple_entries(self):
        h = ConversationHistory()
        for i in range(5):
            h.add(_text_utt("Alice", f"msg {i}"))
        assert len(h) == 5

    def test_overflow_drops_oldest(self):
        h = ConversationHistory(max_entries=3)
        for i in range(5):
            h.add(_text_utt("Alice", f"msg {i}"))
        assert len(h) == 3
        # Oldest two dropped; newest three remain
        texts = [u.text for u in h.all()]
        assert texts == ["msg 2", "msg 3", "msg 4"]

    def test_exactly_at_max_no_drop(self):
        h = ConversationHistory(max_entries=3)
        for i in range(3):
            h.add(_text_utt("Alice", f"msg {i}"))
        assert len(h) == 3

    def test_one_over_max_drops_one(self):
        h = ConversationHistory(max_entries=3)
        for i in range(4):
            h.add(_text_utt("Alice", f"msg {i}"))
        assert len(h) == 3
        assert h.all()[0].text == "msg 1"


# ---------------------------------------------------------------------------
# recent
# ---------------------------------------------------------------------------

class TestRecent:
    def test_recent_returns_last_n(self):
        h = ConversationHistory()
        for i in range(10):
            h.add(_text_utt("A", f"msg {i}"))
        last3 = h.recent(3)
        assert len(last3) == 3
        assert [u.text for u in last3] == ["msg 7", "msg 8", "msg 9"]

    def test_recent_more_than_total_returns_all(self):
        h = ConversationHistory()
        h.add(_text_utt("A", "only one"))
        assert len(h.recent(100)) == 1

    def test_recent_empty_history(self):
        h = ConversationHistory()
        assert h.recent(5) == []

    def test_recent_exactly_n(self):
        h = ConversationHistory()
        for i in range(5):
            h.add(_text_utt("A", f"msg {i}"))
        assert len(h.recent(5)) == 5


# ---------------------------------------------------------------------------
# all
# ---------------------------------------------------------------------------

class TestAll:
    def test_all_returns_full_list(self):
        h = ConversationHistory()
        for i in range(3):
            h.add(_text_utt("A", f"msg {i}"))
        assert len(h.all()) == 3

    def test_all_returns_copy(self):
        h = ConversationHistory()
        h.add(_text_utt("A", "msg"))
        result = h.all()
        result.clear()
        assert len(h.all()) == 1  # original unaffected

    def test_all_empty(self):
        assert ConversationHistory().all() == []


# ---------------------------------------------------------------------------
# to_context_string
# ---------------------------------------------------------------------------

class TestToContextString:
    def test_text_only_format(self):
        h = ConversationHistory()
        h.add(_text_utt("Alice", "Hello there"))
        h.add(_text_utt("Bob", "Hi Alice"))
        ctx = h.to_context_string()
        assert "[Alice]: Hello there" in ctx
        assert "[Bob]: Hi Alice" in ctx

    def test_image_utterance_includes_description(self):
        h = ConversationHistory()
        h.add(_image_utt("Painter", "A sunny landscape", "/tmp/img.png"))
        ctx = h.to_context_string()
        assert "[Painter]" in ctx
        assert "A sunny landscape" in ctx
        assert "generated image" in ctx

    def test_respects_n_limit(self):
        h = ConversationHistory()
        for i in range(10):
            h.add(_text_utt("A", f"msg {i}"))
        ctx = h.to_context_string(n=3)
        assert "msg 9" in ctx
        assert "msg 0" not in ctx

    def test_empty_history_returns_empty_string(self):
        assert ConversationHistory().to_context_string() == ""

    def test_multiple_speakers_all_included(self):
        h = ConversationHistory()
        h.add(_text_utt("Alice", "from Alice", uri="tag:test:alice"))
        h.add(_text_utt("Bob",   "from Bob",   uri="tag:test:bob"))
        ctx = h.to_context_string()
        assert "[Alice]" in ctx
        assert "[Bob]" in ctx


# ---------------------------------------------------------------------------
# __len__
# ---------------------------------------------------------------------------

class TestLen:
    def test_empty(self):
        assert len(ConversationHistory()) == 0

    def test_after_adds(self):
        h = ConversationHistory()
        for i in range(7):
            h.add(_text_utt("A", f"msg {i}"))
        assert len(h) == 7

    def test_after_overflow(self):
        h = ConversationHistory(max_entries=3)
        for i in range(10):
            h.add(_text_utt("A", f"msg {i}"))
        assert len(h) == 3
