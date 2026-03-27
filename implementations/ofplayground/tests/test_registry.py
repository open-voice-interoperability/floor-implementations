"""Tests for AgentRegistry — lookup/storage, case-insensitive by-name search."""
from __future__ import annotations

import pytest

from ofp_playground.agents.registry import AgentRegistry
from ofp_playground.bus.message_bus import MessageBus
from tests.conftest import ConcreteAgent


def _make_agent(name: str, uri_suffix: str) -> ConcreteAgent:
    bus = MessageBus()
    return ConcreteAgent(
        speaker_uri=f"tag:test:{uri_suffix}",
        name=name,
        service_url="local://test",
        bus=bus,
        conversation_id="conv:test",
    )


# ---------------------------------------------------------------------------
# register / get
# ---------------------------------------------------------------------------

class TestRegisterGet:
    def test_register_adds_agent(self):
        reg = AgentRegistry()
        agent = _make_agent("Alice", "alice")
        reg.register(agent)
        assert reg.get(agent.speaker_uri) is agent

    def test_get_unknown_uri_returns_none(self):
        reg = AgentRegistry()
        assert reg.get("tag:test:nonexistent") is None

    def test_register_duplicate_uri_overwrites(self):
        reg = AgentRegistry()
        a1 = _make_agent("Alice", "alice")
        a2 = _make_agent("Alice2", "alice")  # same URI suffix → same speaker_uri
        reg.register(a1)
        reg.register(a2)
        assert reg.get(a1.speaker_uri) is a2

    def test_register_multiple_agents(self):
        reg = AgentRegistry()
        for suffix in ("a", "b", "c"):
            reg.register(_make_agent(suffix.upper(), suffix))
        assert len(reg) == 3


# ---------------------------------------------------------------------------
# unregister
# ---------------------------------------------------------------------------

class TestUnregister:
    def test_unregister_removes_agent(self):
        reg = AgentRegistry()
        agent = _make_agent("Alice", "alice")
        reg.register(agent)
        reg.unregister(agent.speaker_uri)
        assert reg.get(agent.speaker_uri) is None

    def test_unregister_unknown_is_noop(self):
        reg = AgentRegistry()
        reg.unregister("tag:test:ghost")  # should not raise

    def test_unregister_does_not_affect_others(self):
        reg = AgentRegistry()
        a = _make_agent("Alice", "alice")
        b = _make_agent("Bob", "bob")
        reg.register(a)
        reg.register(b)
        reg.unregister(a.speaker_uri)
        assert reg.get(b.speaker_uri) is b


# ---------------------------------------------------------------------------
# all
# ---------------------------------------------------------------------------

class TestAll:
    def test_empty_registry(self):
        assert AgentRegistry().all() == []

    def test_returns_all_registered(self):
        reg = AgentRegistry()
        agents = [_make_agent(f"A{i}", f"a{i}") for i in range(3)]
        for ag in agents:
            reg.register(ag)
        result = reg.all()
        assert set(id(x) for x in result) == set(id(x) for x in agents)

    def test_returns_copy(self):
        reg = AgentRegistry()
        reg.register(_make_agent("Alice", "alice"))
        result = reg.all()
        result.clear()
        assert len(reg.all()) == 1


# ---------------------------------------------------------------------------
# by_name — case-insensitive lookup
# ---------------------------------------------------------------------------

class TestByName:
    def test_exact_match(self):
        reg = AgentRegistry()
        agent = _make_agent("Alice", "alice")
        reg.register(agent)
        assert reg.by_name("Alice") is agent

    def test_case_insensitive_lower(self):
        reg = AgentRegistry()
        agent = _make_agent("Alice", "alice")
        reg.register(agent)
        assert reg.by_name("alice") is agent

    def test_case_insensitive_upper(self):
        reg = AgentRegistry()
        agent = _make_agent("Alice", "alice")
        reg.register(agent)
        assert reg.by_name("ALICE") is agent

    def test_unknown_name_returns_none(self):
        reg = AgentRegistry()
        reg.register(_make_agent("Alice", "alice"))
        assert reg.by_name("Bob") is None

    def test_multiple_agents_correct_match(self):
        reg = AgentRegistry()
        alice = _make_agent("Alice", "alice")
        bob = _make_agent("Bob", "bob")
        reg.register(alice)
        reg.register(bob)
        assert reg.by_name("bob") is bob

    def test_empty_registry_returns_none(self):
        assert AgentRegistry().by_name("Anyone") is None


# ---------------------------------------------------------------------------
# __len__
# ---------------------------------------------------------------------------

class TestLen:
    def test_empty(self):
        assert len(AgentRegistry()) == 0

    def test_after_register(self):
        reg = AgentRegistry()
        for i in range(4):
            reg.register(_make_agent(f"A{i}", f"a{i}"))
        assert len(reg) == 4

    def test_after_unregister(self):
        reg = AgentRegistry()
        a = _make_agent("Alice", "alice")
        reg.register(a)
        reg.unregister(a.speaker_uri)
        assert len(reg) == 0
