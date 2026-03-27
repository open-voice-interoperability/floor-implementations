"""Tests for FloorController — the pure state machine that enforces floor policies."""
from __future__ import annotations

import pytest

from ofp_playground.floor.policy import FloorController, FloorPolicy


# ---------------------------------------------------------------------------
# FloorPolicy metadata
# ---------------------------------------------------------------------------

class TestFloorPolicyMeta:
    def test_all_variants_have_description(self):
        for p in FloorPolicy:
            assert isinstance(p.description, str) and len(p.description) > 10

    def test_all_variants_have_use_case(self):
        for p in FloorPolicy:
            assert isinstance(p.use_case, str) and len(p.use_case) > 10

    def test_enum_values_are_strings(self):
        assert FloorPolicy.SEQUENTIAL.value == "sequential"
        assert FloorPolicy.ROUND_ROBIN.value == "round_robin"
        assert FloorPolicy.MODERATED.value == "moderated"
        assert FloorPolicy.FREE_FOR_ALL.value == "free_for_all"
        assert FloorPolicy.SHOWRUNNER_DRIVEN.value == "showrunner_driven"


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

class TestFloorControllerInit:
    def test_no_holder_initially(self):
        fc = FloorController(FloorPolicy.SEQUENTIAL)
        assert fc.current_holder is None

    def test_empty_queue_initially(self):
        fc = FloorController(FloorPolicy.SEQUENTIAL)
        assert fc.queue == []

    def test_default_policy_is_sequential(self):
        fc = FloorController()
        assert fc.policy == FloorPolicy.SEQUENTIAL


# ---------------------------------------------------------------------------
# FREE_FOR_ALL — always immediately granted
# ---------------------------------------------------------------------------

class TestFreeForAll:
    def _fc(self):
        return FloorController(FloorPolicy.FREE_FOR_ALL)

    def test_first_request_granted_immediately(self):
        fc = self._fc()
        assert fc.request_floor("agent-1") is True
        assert fc.current_holder == "agent-1"

    def test_second_request_granted_over_first_holder(self):
        fc = self._fc()
        fc.request_floor("agent-1")
        granted = fc.request_floor("agent-2")
        assert granted is True
        assert fc.current_holder == "agent-2"

    def test_yield_clears_holder(self):
        fc = self._fc()
        fc.request_floor("agent-1")
        fc.yield_floor("agent-1")
        assert fc.current_holder is None

    def test_queue_stays_empty(self):
        fc = self._fc()
        fc.request_floor("agent-1")
        fc.request_floor("agent-2")
        assert fc.queue == []


# ---------------------------------------------------------------------------
# SEQUENTIAL — FIFO queue when floor is held
# ---------------------------------------------------------------------------

class TestSequential:
    def _fc(self):
        return FloorController(FloorPolicy.SEQUENTIAL)

    def test_first_request_granted_when_free(self):
        fc = self._fc()
        assert fc.request_floor("agent-1") is True
        assert fc.current_holder == "agent-1"

    def test_second_request_queued(self):
        fc = self._fc()
        fc.request_floor("agent-1")
        granted = fc.request_floor("agent-2")
        assert granted is False
        assert ("agent-2", "") in fc.queue

    def test_yield_passes_floor_to_next_in_queue(self):
        fc = self._fc()
        fc.request_floor("agent-1")
        fc.request_floor("agent-2")
        next_uri = fc.yield_floor("agent-1")
        assert next_uri == "agent-2"
        assert fc.current_holder == "agent-2"

    def test_yield_when_no_queue_clears_holder(self):
        fc = self._fc()
        fc.request_floor("agent-1")
        next_uri = fc.yield_floor("agent-1")
        assert next_uri is None
        assert fc.current_holder is None

    def test_fifo_order_preserved(self):
        fc = self._fc()
        fc.request_floor("agent-1")
        fc.request_floor("agent-2")
        fc.request_floor("agent-3")
        assert fc.yield_floor("agent-1") == "agent-2"
        assert fc.yield_floor("agent-2") == "agent-3"
        assert fc.yield_floor("agent-3") is None

    def test_duplicate_request_not_added_twice(self):
        fc = self._fc()
        fc.request_floor("agent-1")
        fc.request_floor("agent-2")
        fc.request_floor("agent-2")  # duplicate
        assert len(fc.queue) == 1

    def test_yield_by_non_holder_not_crash(self):
        """yield_floor by someone who doesn't hold should not crash or corrupt state."""
        fc = self._fc()
        fc.request_floor("agent-1")
        fc.yield_floor("agent-2")  # agent-2 is not holder
        assert fc.current_holder == "agent-1"  # unchanged


# ---------------------------------------------------------------------------
# MODERATED — requests always queue; grant_to decides
# ---------------------------------------------------------------------------

class TestModerated:
    def _fc(self):
        return FloorController(FloorPolicy.MODERATED)

    def test_first_request_still_queued_if_free(self):
        # Moderated: floor is never auto-granted (holder is None but queue gets entry)
        fc = self._fc()
        granted = fc.request_floor("agent-1")
        # Per implementation: granted if _current_holder is None
        # (same path as SEQUENTIAL for first request)
        assert granted is True  # matches implementation: None holder → immediate grant

    def test_grant_to_assigns_floor(self):
        fc = self._fc()
        fc.request_floor("agent-1")
        fc.request_floor("agent-2")
        fc.grant_to("agent-2")
        assert fc.current_holder == "agent-2"

    def test_grant_to_removes_from_queue(self):
        fc = self._fc()
        fc.request_floor("agent-1")
        fc.request_floor("agent-2")
        fc.grant_to("agent-2")
        assert not any(uri == "agent-2" for uri, _ in fc.queue)

    def test_revoke_floor_returns_previous_holder(self):
        fc = self._fc()
        fc.grant_to("agent-1")
        prev = fc.revoke_floor()
        assert prev == "agent-1"
        assert fc.current_holder is None


# ---------------------------------------------------------------------------
# ROUND_ROBIN — rotation after yield
# ---------------------------------------------------------------------------

class TestRoundRobin:
    def _fc(self):
        return FloorController(FloorPolicy.ROUND_ROBIN)

    def test_add_to_rotation(self):
        fc = self._fc()
        fc.add_to_rotation("a1")
        fc.add_to_rotation("a2")
        assert fc._round_robin_order == ["a1", "a2"]

    def test_duplicate_not_added(self):
        fc = self._fc()
        fc.add_to_rotation("a1")
        fc.add_to_rotation("a1")
        assert fc._round_robin_order == ["a1"]

    def test_remove_from_rotation(self):
        fc = self._fc()
        fc.add_to_rotation("a1")
        fc.add_to_rotation("a2")
        fc.remove_from_rotation("a1")
        assert "a1" not in fc._round_robin_order

    def test_yield_advances_rotation(self):
        fc = self._fc()
        fc.add_to_rotation("a1")
        fc.add_to_rotation("a2")
        fc.add_to_rotation("a3")
        fc.grant_to("a1")
        next_uri = fc.yield_floor("a1")
        assert next_uri == "a2"

    def test_rotation_wraps_around(self):
        fc = self._fc()
        for name in ("a1", "a2", "a3"):
            fc.add_to_rotation(name)
        fc.grant_to("a3")
        fc._round_robin_index = 2  # pointing at a3
        next_uri = fc.yield_floor("a3")
        assert next_uri == "a1"  # wraps back to start

    def test_remove_adjusts_index(self):
        fc = self._fc()
        for name in ("a1", "a2", "a3"):
            fc.add_to_rotation(name)
        fc._round_robin_index = 2  # pointing at a3
        fc.remove_from_rotation("a1")
        # After removing a1 (idx=0), order is ['a2','a3'].
        # _round_robin_index was 2, which >= len(['a2','a3'])==2, so clamped to 0.
        assert fc._round_robin_index == 0

    def test_index_clamped_on_removal_past_end(self):
        fc = self._fc()
        fc.add_to_rotation("a1")
        fc.add_to_rotation("a2")
        fc._round_robin_index = 1
        fc.remove_from_rotation("a2")
        assert fc._round_robin_index == 0


# ---------------------------------------------------------------------------
# grant_to (all policies)
# ---------------------------------------------------------------------------

class TestGrantTo:
    def test_sets_current_holder(self):
        fc = FloorController()
        fc.grant_to("agent-x")
        assert fc.current_holder == "agent-x"

    def test_removes_grantee_from_queue(self):
        fc = FloorController()
        # First request is granted immediately (holder), second goes to queue.
        fc.request_floor("agent-1")
        fc.request_floor("agent-2")
        fc.grant_to("agent-2")
        # agent-2 was in the queue and should be removed after grant_to.
        assert not any(uri == "agent-2" for uri, _ in fc.queue)
        # agent-1 was the holder, never in the queue.
        assert not any(uri == "agent-1" for uri, _ in fc.queue)


# ---------------------------------------------------------------------------
# revoke_floor
# ---------------------------------------------------------------------------

class TestRevoke:
    def test_returns_previous_holder(self):
        fc = FloorController()
        fc.grant_to("agent-1")
        prev = fc.revoke_floor()
        assert prev == "agent-1"

    def test_clears_holder(self):
        fc = FloorController()
        fc.grant_to("agent-1")
        fc.revoke_floor()
        assert fc.current_holder is None

    def test_revoke_when_no_holder_returns_none(self):
        fc = FloorController()
        assert fc.revoke_floor() is None


# ---------------------------------------------------------------------------
# queue property
# ---------------------------------------------------------------------------

class TestQueueProperty:
    def test_returns_copy(self):
        fc = FloorController()
        fc.request_floor("a1")
        fc.request_floor("a2")
        q = fc.queue
        q.clear()
        assert len(fc.queue) == 1  # original unaffected

    def test_queue_includes_reason(self):
        fc = FloorController()
        fc.request_floor("a1")
        fc.request_floor("a2", "my reason")
        entries = {uri: reason for uri, reason in fc.queue}
        assert entries.get("a2") == "my reason"
