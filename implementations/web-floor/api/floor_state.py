"""Floor manager state model.

Per-conversation conversant list and floor-granted state, per the Open
Floor Interoperable Conversation Envelope Spec v1.1.1, section 2.2. This is
the single source of truth that used to be split, unsynchronized, across
the browser client and the convener service -- see the architecture plan
for the "why" behind this module's existence.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Optional


def normalize_id(value: Optional[str]) -> str:
    """Normalize a speakerUri/serviceUrl for identity comparison: lowercase,
    strip an "agent:" prefix, strip a trailing slash. Mirrors
    base_strategy_agent.py's _normalize_endpoint_id so the two sides of the
    protocol agree on what "the same conversant" means."""
    if not value:
        return ""
    normalized = str(value).strip().lower()
    if normalized.startswith("agent:"):
        normalized = normalized[len("agent:"):]
    return normalized.rstrip("/")


@dataclass
class ConversantState:
    speaker_uri: str
    service_url: str
    conversational_name: str = ""
    floor_granted: bool = True  # spec default on join (see module docstring); reconciled by the router on invite
    is_convener: bool = False
    accepted: bool = False
    joined_at: float = field(default_factory=time.time)


@dataclass
class ConversationState:
    conv_id: str
    conversants: dict = field(default_factory=dict)  # normalized speaker_uri -> ConversantState
    convener_speaker_uri: Optional[str] = None
    round_history: list = field(default_factory=list)      # [{"speakerUri", "name", "text"}]
    round_turn_order: list = field(default_factory=list)    # normalized speaker_uris granted this round
    # Captured once when a round starts (the human's utterance) and echoed
    # to convener on every delegation/courtesy-copy call for the rest of
    # that round -- a specialist's own reply utterance carries none of this
    # (base_strategy_agent.py's replies only carry text/html features), so
    # convener has no other way to recover it while staying stateless.
    round_question: str = ""
    round_routing_mode: str = ""
    round_max_words: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def get_conversant(self, speaker_uri: str) -> Optional[ConversantState]:
        return self.conversants.get(normalize_id(speaker_uri))

    def get_conversant_by_service_url(self, service_url: str) -> Optional[ConversantState]:
        target = normalize_id(service_url)
        for conversant in self.conversants.values():
            if normalize_id(conversant.service_url) == target:
                return conversant
        return None

    def add_conversant(self, speaker_uri: str, service_url: str, conversational_name: str = "") -> ConversantState:
        key = normalize_id(speaker_uri) or normalize_id(service_url)
        existing = self.conversants.get(key)
        if existing:
            if conversational_name:
                existing.conversational_name = conversational_name
            return existing
        conversant = ConversantState(
            speaker_uri=speaker_uri, service_url=service_url, conversational_name=conversational_name
        )
        self.conversants[key] = conversant
        return conversant

    def remove_conversant(self, speaker_uri: str) -> None:
        self.conversants.pop(normalize_id(speaker_uri), None)

    def start_new_round(self, question: str = "", routing_mode: str = "", max_words: int = 0) -> None:
        self.round_history = []
        self.round_turn_order = []
        self.round_question = question
        self.round_routing_mode = routing_mode
        self.round_max_words = max_words

    def record_turn(self, speaker_uri: str, name: str, text: str) -> None:
        self.round_history.append({"speakerUri": speaker_uri, "name": name, "text": text})
        normalized = normalize_id(speaker_uri)
        if normalized not in self.round_turn_order:
            self.round_turn_order.append(normalized)

    @property
    def convener(self) -> Optional[ConversantState]:
        if not self.convener_speaker_uri:
            return None
        return self.get_conversant(self.convener_speaker_uri)


class ConversationRegistry:
    """Thread-safe registry of ConversationState, keyed by conversation id."""

    def __init__(self):
        self._conversations: dict = {}
        self._lock = threading.Lock()

    def get_or_create(self, conv_id: str) -> ConversationState:
        with self._lock:
            conv = self._conversations.get(conv_id)
            if conv is None:
                conv = ConversationState(conv_id=conv_id)
                self._conversations[conv_id] = conv
            return conv

    def get(self, conv_id: str) -> Optional[ConversationState]:
        with self._lock:
            return self._conversations.get(conv_id)


registry = ConversationRegistry()
