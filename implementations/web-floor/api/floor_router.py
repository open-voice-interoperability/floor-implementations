"""Floor manager routing loop.

Implements the Pass-Through / Delegate-to-Convener event routing table from
the Open Floor Interoperable Conversation Envelope Spec v1.1.1, section 2.2,
operating on plain envelope/event dicts (this project's wire format).

Pure logic: delivery to a conversant's serviceUrl is injected via the
`deliver` callback, so this module has no Flask/network dependency and is
fully unit-testable. flask_gateway.py wires a real HTTP-backed `deliver`.

Phase 1 scope: implements the full table, but delegation/courtesy-copy to a
convener are no-ops until a convener is registered on the ConversationState
(conv.convener_speaker_uri), which Phase 2 adds detection for. Until then,
every event takes the "no convener" column, which this module also fully
implements -- so no rewrite is needed when Phase 2 lands.
"""

import logging
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from floor_state import ConversationState, normalize_id

logger = logging.getLogger(__name__)

UTTERANCE = "utterance"
INVITE = "invite"
UNINVITE = "uninvite"
ACCEPT_INVITE = "acceptInvite"
DECLINE_INVITE = "declineInvite"
BYE = "bye"
GET_MANIFESTS = "getManifests"
PUBLISH_MANIFESTS = "publishManifests"
REQUEST_FLOOR = "requestFloor"
GRANT_FLOOR = "grantFloor"
REVOKE_FLOOR = "revokeFloor"
YIELD_FLOOR = "yieldFloor"

# Events that are always Pass-Through, convener or not (table rows with a
# single behavior in both columns).
PASS_THROUGH_ALWAYS = {DECLINE_INVITE, ACCEPT_INVITE, BYE, GET_MANIFESTS, PUBLISH_MANIFESTS, YIELD_FLOOR}
# Events whose behavior depends on whether a convener is registered.
DELEGATABLE_CONTROL = {INVITE, UNINVITE, REQUEST_FLOOR, GRANT_FLOOR, REVOKE_FLOOR}

MAX_CONCURRENT_DELIVERIES = 8

# Internal-only key stamped onto a reply event by deliver_and_collect, so
# resolve_sender_speaker_uri can later identify which conversant actually
# sent it (a bare reply event carries no sender/dialogEvent of its own).
# Always stripped before an event is shown to the browser or forwarded to
# convener -- see process_envelope's queue.popleft() handling.
_ORIGIN_KEY = "_floorManagerOrigin"

# Report-only key on the copy of each event handed to the caller (the
# returned `executed` list and on_event): who originated it -- the human
# client, the convener, the floor manager itself, or the speaking agent --
# so a client can show a from/to event log. Never on anything delivered to
# a conversant.
_FROM_KEY = "_floorManagerFrom"
# Report-only, alongside _FROM_KEY: the convener that approved an event it
# was delegated by handing it back unchanged (the event is still reported as
# from whoever originally sent it). Carried internally on the returned
# event and popped before anything is delivered.
_VIA_KEY = "_floorManagerVia"
# _ORIGIN_KEY value for events the floor manager generates on its own
# (auto-revoke/grant after invite, the turn cap, convener-registration
# revokes); reported as the floor manager's own speakerUri.
_FLOOR_MANAGER_ORIGIN = "__floor_manager__"


def _event_to(event: dict):
    return event.get("to")


def _to_service_url(to) -> str:
    return to.get("serviceUrl", "") or "" if isinstance(to, dict) else ""


def _to_speaker_uri(to) -> str:
    return to.get("speakerUri", "") or "" if isinstance(to, dict) else ""


def _is_private(event: dict) -> bool:
    to = _event_to(event)
    return bool(isinstance(to, dict) and to.get("private"))


def _event_targets_convener(conv: ConversationState, event: dict) -> bool:
    if not conv.convener_speaker_uri:
        return False
    to = _event_to(event)
    target_speaker = normalize_id(_to_speaker_uri(to))
    target_service = normalize_id(_to_service_url(to))
    convener_speaker = normalize_id(conv.convener_speaker_uri)
    convener_conversant = conv.convener
    convener_service = normalize_id(convener_conversant.service_url) if convener_conversant else ""
    return (target_speaker and target_speaker == convener_speaker) or (target_service and target_service == convener_service)


def _request_floor_subject(conv: ConversationState, event: dict, sender_speaker_uri: str):
    """The conversant a requestFloor is FOR (OFP 1.1.1 sections 0.4.4 and
    1.19: a conversant may request the floor for itself or for another).
    A `to` naming some other conversant means "on behalf of them"; a `to`
    naming the convener -- the spec's own example -- or no `to` at all means
    the requester itself. None when neither is a conversant (e.g. the human
    client), in which case the request's own `to` is used as before."""
    to = _event_to(event)
    named = conv.get_conversant(_to_speaker_uri(to)) or conv.get_conversant_by_service_url(_to_service_url(to))
    requester = conv.get_conversant(sender_speaker_uri)
    if named is not None and not (conv.convener_speaker_uri and normalize_id(named.speaker_uri) == normalize_id(conv.convener_speaker_uri)):
        if requester is None or normalize_id(named.speaker_uri) != normalize_id(requester.speaker_uri):
            return named
    return requester or named


def resolve_sender_speaker_uri(in_envelope: dict, event: dict) -> str:
    """Who actually originated this event occurrence. For an utterance,
    that's who's SPEAKING (dialogEvent.speakerUri) -- not necessarily
    whoever is relaying the envelope. Control-event replies (e.g. an
    acceptInvite handed back by deliver_and_collect) have no dialogEvent
    and no sender of their own -- they're tagged with _ORIGIN_KEY at
    collection time, since deliver_and_collect already knows unambiguously
    which conversant it just talked to. Only an event still carrying
    neither (a genuine top-level event straight from the incoming
    envelope) falls back to the envelope's own sender."""
    if event.get("eventType") == UTTERANCE:
        params = event.get("parameters") or {}
        dialog = params.get("dialogEvent") or event.get("dialogEvent") or {}
        speaker = dialog.get("speakerUri")
        if speaker:
            return speaker
    origin = event.get(_ORIGIN_KEY)
    if origin:
        return origin
    sender = _unwrap_envelope(in_envelope).get("sender") or {}
    return sender.get("speakerUri", "")


def _unwrap_envelope(envelope: dict) -> dict:
    return envelope.get("openFloor") or envelope.get("openfloor") or envelope.get("ovon") or envelope


def sender_currently_holds_floor(conv: ConversationState, sender_speaker_uri: str) -> bool:
    """True for the human (never tracked as a conversant -- always
    implicitly allowed to speak) or any conversant currently floor_granted."""
    conversant = conv.get_conversant(sender_speaker_uri)
    if conversant is None:
        return True
    return conversant.floor_granted


def _dialog_event(event: dict) -> dict:
    params = event.get("parameters") or {}
    return params.get("dialogEvent") or event.get("dialogEvent") or {}


def _extract_utterance_text(event: dict) -> str:
    dialog = _dialog_event(event)
    tokens = ((dialog.get("features") or {}).get("text") or {}).get("tokens") or []
    return " ".join((t.get("value", "") if isinstance(t, dict) else str(t)) for t in tokens).strip()


def _extract_dialog_feature_value(event: dict, feature_name: str) -> str:
    """A convener-set feature on the dialogEvent (e.g. "routingMode",
    "maxWords") -- same shape as the "text" feature, just a different key,
    matching how app.js/convener.py already encode these."""
    dialog = _dialog_event(event)
    feature = (dialog.get("features") or {}).get(feature_name) or {}
    tokens = feature.get("tokens") or []
    if not tokens:
        return ""
    first = tokens[0]
    return (first.get("value", "") if isinstance(first, dict) else str(first)).strip()


def resolve_pass_through_targets(conv: ConversationState, event: dict, sender_speaker_uri: str) -> list:
    """Conversants (ConversantState) this event should be delivered to,
    honoring the utterance `to.private` narrowing. Never includes the
    sender itself.

    An UTTERANCE also never includes the registered convener in this plain
    broadcast -- convener gets its own separate, richer delivery instead
    (delegation or courtesy-copy, carrying the conversant roster and round
    context), so it's never called twice for the same utterance.

    Every OTHER Pass-Through-Always event type (acceptInvite,
    declineInvite, bye, getManifests, publishManifests, yieldFloor) has no
    such alternate delivery to convener, so convener is NOT excluded for
    those -- it's just another conversant on the broadcast, per the spec's
    own Pass-Through semantics. Excluding it there silently meant convener
    could never learn a specialist it had asked to be invited actually
    accepted (confirmed live: acceptInvite from a newly invited specialist
    never reached the convener that requested the invite at all)."""
    to = _event_to(event)
    event_type = event.get("eventType")
    if event_type == UTTERANCE and _is_private(event):
        target_speaker = _to_speaker_uri(to)
        target_service = _to_service_url(to)
        if target_speaker:
            match = conv.get_conversant(target_speaker)
            if match:
                return [match]
        if target_service:
            match = conv.get_conversant_by_service_url(target_service)
            if match:
                return [match]
        return []
    sender_normalized = normalize_id(sender_speaker_uri)
    exclude_convener = event_type == UTTERANCE and conv.convener_speaker_uri
    convener_normalized = normalize_id(conv.convener_speaker_uri) if exclude_convener else None
    return [
        c for c in conv.conversants.values()
        if normalize_id(c.speaker_uri) != sender_normalized and normalize_id(c.speaker_uri) != convener_normalized
    ]


def _conversants_payload(conv) -> list:
    """Build the OFP conversation.conversants array for an outbound
    envelope: the identification block of every conversant currently on
    conv's floor. Shared by _build_outbound_envelope (every agent-facing
    delivery) and _call_convener's floorGranted-augmented version, so a
    recipient agent can see who else (if anyone) is on the floor -- e.g.
    base_strategy_agent.py's scope gate uses this to tell "I'm the only
    agent here, a decline message is useful" apart from "some other
    conversant can presumably handle this, stay silent"."""
    return [
        {
            "identification": {
                "speakerUri": c.speaker_uri,
                "serviceUrl": c.service_url,
                "conversationalName": c.conversational_name,
                # organization/synopsis are mandatory (non-Optional) fields
                # on the openfloor package's Identification dataclass --
                # empty strings are structurally valid, and callers only
                # ever read speakerUri/serviceUrl/conversationalName back
                # out of this list, so no information is actually lost.
                "organization": "",
                "synopsis": "",
            }
        }
        for c in conv.conversants.values()
    ]


def _build_outbound_envelope(floor_manager_identity: dict, conv, event: dict) -> dict:
    return {
        "openFloor": {
            "schema": {"version": "1.1", "url": "https://openvoicenetwork.org/schema"},
            "conversation": {"id": conv.conv_id, "conversants": _conversants_payload(conv)},
            "sender": floor_manager_identity,
            "events": [event],
        }
    }


_FLOOR_HOLDER_FEATURE = "floorHolder"
_RESUME_FEATURE = "resumeAfterFloorHolder"


def _event_features(event: dict) -> dict:
    params = event.get("parameters") or {}
    dialog = params.get("dialogEvent") or event.get("dialogEvent") or {}
    return dialog.get("features") or {}


def _first_floor_holder(events) -> "dict | None":
    """The first reply event that is a transient "floor holder" status
    (an utterance flagged with the floorHolder feature) rather than the
    agent's actual answer -- see base_strategy_agent.py's _append_floor_holder."""
    for e in events or []:
        if isinstance(e, dict) and e.get("eventType") == UTTERANCE and _FLOOR_HOLDER_FEATURE in _event_features(e):
            return e
    return None


def _clean_event(event: dict) -> dict:
    e = dict(event)
    e.pop(_ORIGIN_KEY, None)
    e.pop(_TRUSTED_KEY, None)
    return e


def _build_resume_event(conversant, original_event: dict, conv, floor_manager_identity: dict) -> dict:
    """The gateway's follow-up request after a floor holder: asks `conversant`
    to hand back the answer whose work it has been running since the first
    request. Delivered straight to that conversant -- it never enters the
    routing table."""
    return {
        "eventType": UTTERANCE,
        "to": {"speakerUri": conversant.speaker_uri, "serviceUrl": conversant.service_url},
        "parameters": {"dialogEvent": {
            "id": f"resume:{normalize_id(conv.conv_id) or 'conv'}",
            "speakerUri": floor_manager_identity.get("speakerUri", ""),
            "span": {"startTime": datetime.now(timezone.utc).isoformat()},
            "features": {
                "text": {"tokens": [{"value": _extract_utterance_text(original_event)}]},
                _RESUME_FEATURE: {"tokens": [{"value": conv.conv_id}]},
            },
        }},
    }


def deliver_and_collect(conversant, event: dict, floor_manager_identity: dict, conv, deliver, timeout: float, on_progress=None, on_event=None) -> list:
    """Send `event` to one conversant's serviceUrl via the injected
    `deliver` callback; returns whatever event dicts it replied with (an
    empty list on failure -- delivery failures must never abort the round).
    Each reply is stamped with _ORIGIN_KEY: this call is a direct
    request/response against `conversant`, so any events it hands back
    unambiguously originated there, even though the reply itself carries
    no sender/dialogEvent of its own (e.g. a bare acceptInvite).

    `on_progress(speaker_uri, service_url, status)` -- status "working" then
    "idle" -- is an optional live progress hook, called around the actual
    network call so a caller (e.g. flask_gateway.py's streaming endpoint)
    can surface real per-conversant activity to a client. May be called from
    a worker thread when reached via deliver_concurrently's thread pool, so
    it must be safe to call concurrently (a thread-safe queue.put is).

    `on_event(event)` -- when the conversant returns a "floor holder" status
    instead of its answer (its real work is still running), that status is
    streamed via on_event immediately and a resume request is sent to
    collect the finished answer, which is what this function then returns.
    Agents that don't use the protocol just answer normally and this is a
    no-op."""
    envelope = _build_outbound_envelope(floor_manager_identity, conv, event)
    if on_progress:
        on_progress(conversant.speaker_uri, conversant.service_url, "working")
    try:
        events = _deliver_with_retry(conversant, envelope, deliver, timeout)
        holder = _first_floor_holder(events)
        if holder is not None:
            if on_event:
                on_event({**_clean_event(holder), _FROM_KEY: conversant.speaker_uri})
            resume_event = _build_resume_event(conversant, event, conv, floor_manager_identity)
            resume_env = _build_outbound_envelope(floor_manager_identity, conv, resume_event)
            events = _deliver_with_retry(conversant, resume_env, deliver, timeout)
    finally:
        if on_progress:
            on_progress(conversant.speaker_uri, conversant.service_url, "idle")
    for reply_event in events:
        if isinstance(reply_event, dict):
            reply_event[_ORIGIN_KEY] = conversant.speaker_uri
    return events


def _is_timeout_error(error: Exception) -> bool:
    """True for a genuine timeout, whether raised directly (TimeoutError /
    socket.timeout, which is TimeoutError as of Python 3.10) or wrapped
    inside another exception's .reason (urllib.error.URLError's shape for
    a connect-phase timeout) -- checked via duck typing so this stays
    transport-agnostic rather than importing a specific HTTP library."""
    if isinstance(error, TimeoutError):
        return True
    return isinstance(getattr(error, "reason", None), TimeoutError)


def _deliver_with_retry(conversant, envelope: dict, deliver, timeout: float) -> list:
    """A single transient, FAST-failing delivery error (a dropped
    connection, an agent process mid-restart) must not silently lose that
    conversant's whole turn for the round -- confirmed live: an agent
    crash mid-conversation looks exactly like "that conversant's results
    just never showed up," with nothing in the floor manager's own logs to
    explain why (delivery failures used to be swallowed with no logging at
    all). One immediate retry, without backoff, rides out that kind of
    momentary hiccup.

    A genuine TIMEOUT is handled differently on purpose: the full `timeout`
    has already been spent waiting once, so retrying would just spend it
    again for no benefit -- give up immediately rather than doubling the
    wait, and log that the agent was unavailable."""
    try:
        return deliver(conversant.service_url, envelope, timeout) or []
    except Exception as first_error:
        if _is_timeout_error(first_error):
            logger.warning(
                "Agent at %s is unavailable (timed out after %.0fs) -- giving up on this turn",
                conversant.service_url, timeout,
            )
            return []
        logger.warning("Delivery to %s failed (%s), retrying once", conversant.service_url, first_error)

    try:
        return deliver(conversant.service_url, envelope, timeout) or []
    except Exception as second_error:
        logger.warning(
            "Agent at %s is unavailable (failed again after retry: %s) -- giving up on this turn",
            conversant.service_url, second_error,
        )
        return []


def deliver_concurrently(targets: list, event: dict, floor_manager_identity: dict, conv, deliver, timeout: float, on_progress=None, on_event=None) -> list:
    """Deliver `event` to every target concurrently (they're independent
    recipients of the same one event -- the spec's normative
    sequential-processing rule governs the EVENT QUEUE, not fan-out to
    multiple recipients of a single Pass-Through). Results are collected
    and returned in stable target order so downstream queueing stays
    deterministic."""
    if not targets:
        return []
    if len(targets) == 1:
        return deliver_and_collect(targets[0], event, floor_manager_identity, conv, deliver, timeout, on_progress, on_event)
    with ThreadPoolExecutor(max_workers=min(MAX_CONCURRENT_DELIVERIES, len(targets))) as pool:
        futures = [
            pool.submit(deliver_and_collect, target, event, floor_manager_identity, conv, deliver, timeout, on_progress, on_event)
            for target in targets
        ]
        results = [f.result() for f in futures]
    return [event for events in results for event in events]


def apply_local_state(conv: ConversationState, event: dict, sender_speaker_uri: str) -> list:
    """Update conv's conversant list / floor state as a side effect of
    processing an event. Returns any additional events the floor manager
    itself wants to execute as a result (e.g. auto-revoke-after-invite,
    or the no-convener requestFloor->grantFloor rule)."""
    event_type = event.get("eventType")
    to = _event_to(event)

    if event_type == INVITE:
        speaker_uri = _to_speaker_uri(to)
        service_url = _to_service_url(to)
        if not (speaker_uri or service_url):
            return []
        conversant = conv.add_conversant(speaker_uri or service_url, service_url or speaker_uri)
        # Spec default is floorGranted=True the moment a conversant is added
        # (curation rule, section 2.2). With a convener registered, this
        # project deliberately reconciles that down to revoked immediately so
        # the convener decides who speaks -- see base_strategy_agent.py's
        # _handle_invite for the matching agent-side deviation/rationale.
        # With no convener, nobody would ever grant it back, so instead send
        # an explicit grantFloor: agents that gate locally on grantFloor
        # (base_strategy_agent.py) then agree with the router's state. A
        # convener that registers later revokes everyone (see
        # _revoke_all_on_convener_registration).
        conversant.floor_granted = True
        to_conversant = {"speakerUri": conversant.speaker_uri, "serviceUrl": conversant.service_url}
        if conv.convener_speaker_uri:
            return [{"eventType": REVOKE_FLOOR, "to": to_conversant, _ORIGIN_KEY: _FLOOR_MANAGER_ORIGIN}]
        return [{"eventType": GRANT_FLOOR, "to": to_conversant, _TRUSTED_KEY: True, _ORIGIN_KEY: _FLOOR_MANAGER_ORIGIN}]

    if event_type == UNINVITE:
        target = conv.get_conversant(_to_speaker_uri(to)) or conv.get_conversant_by_service_url(_to_service_url(to))
        if target:
            conv.remove_conversant(target.speaker_uri)
        return []

    if event_type in (DECLINE_INVITE, BYE):
        conversant = conv.get_conversant(sender_speaker_uri)
        if conversant:
            conv.remove_conversant(conversant.speaker_uri)
        return []

    if event_type == ACCEPT_INVITE:
        conversant = conv.get_conversant(sender_speaker_uri)
        if conversant:
            conversant.accepted = True
        return []

    if event_type in (GRANT_FLOOR, REVOKE_FLOOR):
        target = conv.get_conversant(_to_speaker_uri(to)) or conv.get_conversant_by_service_url(_to_service_url(to))
        if target:
            target.floor_granted = event_type == GRANT_FLOOR
            if event_type == GRANT_FLOOR:
                target.turn_capped = False
        return []

    if event_type == YIELD_FLOOR:
        conversant = conv.get_conversant(sender_speaker_uri)
        if conversant:
            conversant.floor_granted = False
        return []

    return []


_TRUSTED_KEY = "_floorManagerTrusted"


def process_envelope(conv: ConversationState, in_envelope: dict, floor_manager_identity: dict, deliver, timeout: float = 30.0, on_progress=None, on_event=None) -> list:
    """Process every event in in_envelope's "openFloor.events" list per the
    routing table, returning the ordered list of events the caller (browser
    or convener) should be shown/rendered.

    `on_progress(speaker_uri, service_url, status)` is an optional live
    progress hook (see deliver_and_collect) threaded through to every
    delivery call this makes, so a streaming caller can surface real-time
    per-conversant activity instead of only a final aggregated result.

    `on_event(event)` is an optional hook called the moment an event is
    finalized into `executed` -- e.g. the instant one specialist's reply is
    ready, not after the whole round (which can take minutes across many
    conversants) finishes. A streaming caller uses this to show each
    response as it arrives instead of batching everything until the end."""
    openfloor = _unwrap_envelope(in_envelope)
    raw_events = openfloor.get("events") or []
    queue = deque(raw_events)
    executed = []

    def finalize(event: dict, sender: str, via: str = "") -> None:
        # Report a copy tagged with who originated it (see _FROM_KEY); the
        # original may still be delivered to a conversant afterwards.
        reported = {k: v for k, v in event.items() if k not in (_ORIGIN_KEY, _TRUSTED_KEY, _VIA_KEY)}
        origin = floor_manager_identity.get("speakerUri", "") if sender == _FLOOR_MANAGER_ORIGIN else sender
        if origin:
            reported[_FROM_KEY] = origin
        if via:
            reported[_VIA_KEY] = via
        executed.append(reported)
        if on_event:
            on_event(reported)

    while queue:
        event = queue.popleft()
        # Events the convener itself returned are privileged: execute them
        # directly, never re-delegate them back to convener (which would
        # loop forever -- convener would just be asked "what do you want to
        # do about the event you just told me to do" indefinitely).
        trusted = event.pop(_TRUSTED_KEY, False)
        event_type = event.get("eventType")
        sender_speaker_uri = resolve_sender_speaker_uri(in_envelope, event)
        event.pop(_ORIGIN_KEY, None)
        via = event.pop(_VIA_KEY, "")

        if event_type == UTTERANCE:
            if not trusted and not sender_currently_holds_floor(conv, sender_speaker_uri):
                if conv.convener_speaker_uri:
                    convener_events = delegate_to_convener(conv, event, sender_speaker_uri, floor_manager_identity, deliver, timeout, on_progress)
                    queue.extendleft(reversed(convener_events))
                # else: Ignore, per table.
                continue

            # Round bookkeeping, so convener can stay stateless: a fresh
            # utterance from someone who isn't a tracked conversant is the
            # human starting a new round (captures the question/mode for
            # every later delegation call this round); a genuine specialist
            # conversant's own reply records its turn before it's
            # courtesy-copied onward. The registered convener's own
            # synthesized private utterances (trusted, re-issuing a question
            # alongside a floor grant) are neither -- they're not a new
            # question and not a specialist's answer.
            is_convener_sender = bool(conv.convener_speaker_uri) and normalize_id(sender_speaker_uri) == normalize_id(conv.convener_speaker_uri)
            sender_conversant = conv.get_conversant(sender_speaker_uri)
            if sender_conversant is None:
                conv.start_new_round(
                    question=_extract_utterance_text(event),
                    routing_mode=_extract_dialog_feature_value(event, "routingMode"),
                    max_words=int(_extract_dialog_feature_value(event, "maxWords") or 0),
                )
                if not conv.convener_speaker_uri:
                    # No convener to hand the floor back after last round's
                    # one-comment-per-turn cap -- restore it ourselves, before
                    # this new question goes out, so capped specialists can
                    # answer it. Explicit human/agent revokes are left alone.
                    for capped in [c for c in conv.conversants.values() if c.turn_capped]:
                        grant_event = {
                            "eventType": GRANT_FLOOR,
                            "to": {"speakerUri": capped.speaker_uri, "serviceUrl": capped.service_url},
                        }
                        grant_replies = deliver_and_collect(capped, grant_event, floor_manager_identity, conv, deliver, timeout, on_progress)
                        apply_local_state(conv, grant_event, sender_speaker_uri)
                        finalize(grant_event, _FLOOR_MANAGER_ORIGIN)
                        queue.extend(grant_replies)
            elif not is_convener_sender:
                conv.record_turn(sender_speaker_uri, sender_conversant.conversational_name, _extract_utterance_text(event))

            # Cap each specialist to one comment per turn so peer-to-peer
            # cross-talk can't cascade: the moment a specialist's own reply
            # is about to be broadcast to its peers (Pass-Through, below),
            # close ITS OWN local floor gate first via a real, synchronously
            # delivered revokeFloor -- so by the time any peer's reply comes
            # back around, this conversant no longer holds the floor and
            # won't be re-triggered. Skipped for exactly 2 non-convener
            # conversants, so a pair of specialists can freely converse.
            #
            # The revokeFloor is delivered/applied here (early), but NOT
            # finalized yet -- finalize it AFTER this specialist's own
            # utterance below instead. A streaming caller finalizes/shows
            # events in the order it receives them, and a client-side
            # "don't show an utterance from an already-revoked speaker"
            # guard (a real one exists in web-floor's app.js, for a
            # DIFFERENT, legitimate case: a stale/late reply arriving after
            # that speaker was revoked for some other reason) would
            # otherwise see this specialist as already revoked by the time
            # its own triggering utterance arrives, and wrongly suppress it
            # -- confirmed live: this made every >2-specialist reply vanish
            # from the conversation history while still showing in the raw
            # event log.
            pending_self_revoke = None
            # Only without a convener: when one is registered it decides
            # who holds the floor, and it already revokes every agent that
            # speaks (convener.py's _decide_for_specialist_reply, and its
            # guest handling) via the courtesy copy below. Its revoke is
            # queued ahead of any replies this broadcast triggers, so the
            # speaker is closed before a peer's answer could re-trigger it
            # -- the same guarantee this cap gives -- and capping here as
            # well just doubled every revoke.
            if not is_convener_sender and sender_conversant is not None and not conv.convener_speaker_uri:
                other_conversants = [
                    c for c in conv.conversants.values()
                    if not (conv.convener_speaker_uri and normalize_id(c.speaker_uri) == normalize_id(conv.convener_speaker_uri))
                ]
                if len(other_conversants) > 2 and sender_conversant.floor_granted:
                    revoke_event = {
                        "eventType": REVOKE_FLOOR,
                        "to": {"speakerUri": sender_conversant.speaker_uri, "serviceUrl": sender_conversant.service_url},
                    }
                    revoke_replies = deliver_and_collect(sender_conversant, revoke_event, floor_manager_identity, conv, deliver, timeout, on_progress)
                    apply_local_state(conv, revoke_event, sender_speaker_uri)
                    sender_conversant.turn_capped = True
                    pending_self_revoke = revoke_event
                    queue.extend(revoke_replies)

            targets = resolve_pass_through_targets(conv, event, sender_speaker_uri)
            reply_events = deliver_concurrently(targets, event, floor_manager_identity, conv, deliver, timeout, on_progress, on_event)
            # NOT finalize()-ing reply_events here -- each reply re-enters
            # the SAME table (queue.extend below) and gets finalized exactly
            # once, when ITS OWN turn through the loop reaches the
            # "finalize(event)" below. Finalizing it here too would
            # double-report every specialist reply.
            queue.extend(reply_events)  # each reply re-enters the SAME table, at the tail

            if not trusted and conv.convener_speaker_uri:
                courtesy_events = deliver_courtesy_copy_to_convener(conv, event, sender_speaker_uri, floor_manager_identity, deliver, timeout, on_progress)
                queue.extendleft(reversed(courtesy_events))

            finalize(event, sender_speaker_uri, via)
            if pending_self_revoke is not None:
                finalize(pending_self_revoke, _FLOOR_MANAGER_ORIGIN)
            continue

        if event_type in DELEGATABLE_CONTROL:
            # A control event TARGETING the convener itself (e.g. the
            # auto-revoke this router issues right after any invite,
            # including inviting the convener) must never be delegated to
            # that same convener for a decision: convener would trivially
            # echo it back unchanged (still carrying the delegation
            # envelope's roundHistory parameters), the router would then
            # deliver that "approved" event to its target -- which is
            # convener again -- and convener would see the same
            # roundHistory marker and treat the delivery as a fresh
            # delegation request, echoing forever. Deciding about its own
            # floor rights isn't a meaningful question for convener to
            # answer anyway, so this always executes directly instead.
            if event_type == REQUEST_FLOOR:
                # A request's `to` is normally whoever decides it (the
                # spec's own example addresses the convener) -- what counts
                # is who it's FOR. See _request_floor_subject.
                subject = _request_floor_subject(conv, event, sender_speaker_uri)
                target_is_convener = (
                    bool(subject) and bool(conv.convener_speaker_uri)
                    and normalize_id(subject.speaker_uri) == normalize_id(conv.convener_speaker_uri)
                )
            else:
                subject = None
                target_is_convener = _event_targets_convener(conv, event)
            if not trusted and conv.convener_speaker_uri and not target_is_convener:
                if event_type == REQUEST_FLOOR:
                    # Report the request itself (with its reason) -- the
                    # convener answers with a grantFloor or revokeFloor of
                    # its own, which is reported when it's executed.
                    finalize(event, sender_speaker_uri)
                convener_events = delegate_to_convener(conv, event, sender_speaker_uri, floor_manager_identity, deliver, timeout, on_progress)
                queue.extendleft(reversed(convener_events))
                continue

            # Trusted (convener-originated), targeting convener itself, or
            # no convener registered: per table, requestFloor -> auto
            # grantFloor; the rest execute as given.
            if event_type == REQUEST_FLOOR:
                grant_to = {"speakerUri": subject.speaker_uri, "serviceUrl": subject.service_url} if subject else event.get("to")
                resolved = {"eventType": GRANT_FLOOR, "to": grant_to}
            else:
                resolved = event
            to = _event_to(resolved)

            # The convener manages the floor; it never holds it, so a
            # grantFloor/revokeFloor addressed to it is neither sent nor
            # reported. Seen live: inviting the convener got it the grant
            # every conversant gets while there's no convener, and its
            # registration then revoked it again -- two meaningless events.
            if resolved.get("eventType") in (GRANT_FLOOR, REVOKE_FLOOR) and _is_convener_target(conv, to):
                convener = conv.convener
                if convener is not None:
                    convener.floor_granted = False
                continue

            if event_type == INVITE:
                # apply_local_state creates the conversant for invite -- resolve
                # the target AFTER, from what it just added.
                extra = apply_local_state(conv, resolved, sender_speaker_uri)
                target = conv.get_conversant(_to_speaker_uri(to)) or conv.get_conversant_by_service_url(_to_service_url(to))
            else:
                # uninvite removes the conversant -- resolve the target BEFORE,
                # so we still have its serviceUrl to actually deliver to (a
                # captured object reference stays valid even once removed
                # from conv.conversants).
                target = conv.get_conversant(_to_speaker_uri(to)) or conv.get_conversant_by_service_url(_to_service_url(to))
                extra = apply_local_state(conv, resolved, sender_speaker_uri)

            if event_type == REQUEST_FLOOR:
                # Report both halves: the request from whoever asked (unless
                # it was already reported when it was delegated and the
                # convener handed it back), then the grant from whoever
                # decided it -- that convener, or the floor manager itself.
                if not trusted:
                    finalize(event, sender_speaker_uri)
                finalize(resolved, via or _FLOOR_MANAGER_ORIGIN)
            else:
                finalize(resolved, sender_speaker_uri, via)

            # Pass-Through: the resolved event must actually reach its target
            # conversant -- apply_local_state above only updates the floor
            # manager's OWN bookkeeping; delivery is what flips the agent's
            # own local floor gate (e.g. base_strategy_agent.py's
            # _floor_granted), which is the real point of grantFloor/revokeFloor.
            if target is not None:
                reply_events = deliver_and_collect(target, resolved, floor_manager_identity, conv, deliver, timeout, on_progress)
                # NOT finalize()-ing reply_events -- same reasoning as the
                # utterance branch above: each reply (e.g. an acceptInvite in
                # response to this invite) re-enters the table via
                # queue.extend and gets finalized exactly once when its own
                # turn through the loop is processed.
                queue.extend(reply_events)

            queue.extend(extra)
            continue

        if event_type in PASS_THROUGH_ALWAYS:
            targets = resolve_pass_through_targets(conv, event, sender_speaker_uri)
            reply_events = deliver_concurrently(targets, event, floor_manager_identity, conv, deliver, timeout, on_progress)
            for reply_event in reply_events:
                finalize(reply_event, reply_event.get(_ORIGIN_KEY) or sender_speaker_uri)
            apply_local_state(conv, event, sender_speaker_uri)
            if event_type == ACCEPT_INVITE and not conv.convener_speaker_uri:
                accepting_conversant = conv.get_conversant(sender_speaker_uri)
                if accepting_conversant is not None:
                    if detect_convener_role(conv, accepting_conversant, floor_manager_identity, deliver, timeout):
                        queue.extend(_revoke_all_on_convener_registration(conv))
            finalize(event, sender_speaker_uri, via)
            continue

        # Unknown event type: report it unchanged, do nothing else.
        finalize(event, sender_speaker_uri, via)

    return executed


def _is_convener_target(conv: ConversationState, to) -> bool:
    """True when ``to`` addresses this conversation's registered convener."""
    if not conv.convener_speaker_uri or not to:
        return False
    convener = conv.convener
    ids = {normalize_id(conv.convener_speaker_uri)}
    if convener is not None:
        ids.add(normalize_id(convener.service_url))
    return bool({normalize_id(v) for v in (_to_speaker_uri(to), _to_service_url(to)) if v} & ids)


def _revoke_all_on_convener_registration(conv: ConversationState) -> list:
    """Conversants invited before any convener joined were granted the floor
    (see apply_local_state's invite handling). Once a convener registers it
    decides who speaks, so revoke everyone still holding the floor, matching
    the state they'd be in had the convener been present when they were
    invited. Not the convener itself: it manages the floor and never holds
    it, so it is only marked revoked here, without an event. Trusted: these
    are the floor manager's own reconciliation, not something to delegate."""
    convener = conv.convener
    if convener is not None:
        convener.floor_granted = False
    return [
        {"eventType": REVOKE_FLOOR, "to": {"speakerUri": c.speaker_uri, "serviceUrl": c.service_url},
         _TRUSTED_KEY: True, _ORIGIN_KEY: _FLOOR_MANAGER_ORIGIN}
        for c in conv.conversants.values()
        if c.floor_granted
    ]


def detect_convener_role(conv: ConversationState, conversant, floor_manager_identity: dict, deliver, timeout: float) -> bool:
    """Fetch `conversant`'s manifest and register it as this conversation's
    convener if it declares openFloorRoles.convener=true. Called right
    after a conversant accepts its invite (the natural point at which the
    floor manager needs to know whether it just gained a convener),
    without waiting for the convener to be discovered any other way (no
    hardcoded port numbers -- works for any Open-Floor-compliant convener)."""
    envelope = _build_outbound_envelope(floor_manager_identity, conv, {"eventType": GET_MANIFESTS})
    try:
        events = deliver(conversant.service_url, envelope, timeout) or []
    except Exception:
        return False
    for reply_event in events:
        if not isinstance(reply_event, dict) or reply_event.get("eventType") != PUBLISH_MANIFESTS:
            continue
        manifests = (reply_event.get("parameters") or {}).get("servicingManifests") or []
        for manifest in manifests:
            identification = (manifest or {}).get("identification") or {}
            roles = identification.get("openFloorRoles") or {}
            if roles.get("convener"):
                conversant.is_convener = True
                conv.convener_speaker_uri = conversant.speaker_uri
                return True
    return False


def delegate_to_convener(conv, event, sender_speaker_uri, floor_manager_identity, deliver, timeout, on_progress=None):
    return _call_convener(conv, event, sender_speaker_uri, floor_manager_identity, deliver, timeout, on_progress)


def deliver_courtesy_copy_to_convener(conv, event, sender_speaker_uri, floor_manager_identity, deliver, timeout, on_progress=None):
    return _call_convener(conv, event, sender_speaker_uri, floor_manager_identity, deliver, timeout, on_progress)


def _is_unchanged_approval(returned_event: dict, delegated_event: dict) -> bool:
    """A delegated control event the convener handed back as-is (same type,
    same target) -- its approval, not a decision of its own."""
    if returned_event.get("eventType") != delegated_event.get("eventType") or returned_event.get("eventType") == UTTERANCE:
        return False
    def ids(event):
        to = _event_to(event) or {}
        return {normalize_id(v) for v in (_to_speaker_uri(to), _to_service_url(to)) if v}

    a, b = ids(returned_event), ids(delegated_event)
    return a == b or bool(a & b)


def _call_convener(conv, event, sender_speaker_uri, floor_manager_identity, deliver, timeout, on_progress=None):
    convener = conv.convener
    if convener is None:
        return []
    envelope = _build_outbound_envelope(floor_manager_identity, conv, event)
    openfloor = envelope["openFloor"]
    # conversants is already populated by _build_outbound_envelope (via
    # _conversants_payload) -- only floorGranted is specific to this call.
    # Spec section 1.6: floorGranted is "an array of speakerURIs", not
    # serviceUrls -- speakerUri and serviceUrl happen to be identical for
    # every agent in this project's own examples, which is what let this
    # go unnoticed; a genuinely spec-compliant participant (or this
    # project's own tag:-URI manifest fallback) would have them differ.
    openfloor["conversation"]["floorGranted"] = [c.speaker_uri for c in conv.conversants.values() if c.floor_granted]
    openfloor["events"][0] = {
        **event,
        "parameters": {
            **(event.get("parameters") or {}),
            "roundHistory": list(conv.round_history),
            "roundTurnOrder": list(conv.round_turn_order),
            "roundQuestion": conv.round_question,
            "roundRoutingMode": conv.round_routing_mode,
            "roundMaxWords": conv.round_max_words,
        },
    }
    if on_progress:
        on_progress(convener.speaker_uri, convener.service_url, "working")
    try:
        returned_events = _deliver_with_retry(convener, envelope, deliver, timeout)
    finally:
        if on_progress:
            on_progress(convener.speaker_uri, convener.service_url, "idle")
    # Trust whatever convener sends back -- it's privileged, per the spec's
    # own wording ("the convener is then responsible for returning this
    # event back to the floor manager OR substituting it with different
    # events"). Marked so process_envelope executes these directly instead
    # of re-delegating them back to convener.
    for returned_event in returned_events:
        if isinstance(returned_event, dict):
            returned_event[_TRUSTED_KEY] = True
            if returned_event.get("eventType") == UTTERANCE:
                # An utterance in someone else's voice (e.g. relaying the
                # user's private question to the one specialist it was for)
                # is relayed by the convener, not said by it.
                speaker = ((returned_event.get("parameters") or {}).get("dialogEvent") or {}).get("speakerUri", "")
                if speaker and normalize_id(speaker) != normalize_id(convener.speaker_uri):
                    returned_event[_VIA_KEY] = convener.speaker_uri
                returned_event.setdefault(_ORIGIN_KEY, convener.speaker_uri)
            elif sender_speaker_uri and _is_unchanged_approval(returned_event, event):
                # Handed back as-is: still the original sender's event,
                # approved by the convener.
                returned_event.setdefault(_ORIGIN_KEY, sender_speaker_uri)
                returned_event[_VIA_KEY] = convener.speaker_uri
            else:
                returned_event.setdefault(_ORIGIN_KEY, convener.speaker_uri)
    return returned_events
