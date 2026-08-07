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

from collections import deque
from concurrent.futures import ThreadPoolExecutor

from floor_state import ConversationState, normalize_id

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
    sender itself. For a public (non-private) broadcast, also never
    includes the registered convener -- the convener always gets its own
    separate, richer delivery (delegation or courtesy-copy, carrying the
    conversant roster and round context), never the plain broadcast copy,
    so it's never called twice for the same event."""
    to = _event_to(event)
    if event.get("eventType") == UTTERANCE and _is_private(event):
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
    convener_normalized = normalize_id(conv.convener_speaker_uri) if conv.convener_speaker_uri else None
    return [
        c for c in conv.conversants.values()
        if normalize_id(c.speaker_uri) != sender_normalized and normalize_id(c.speaker_uri) != convener_normalized
    ]


def _build_outbound_envelope(floor_manager_identity: dict, conv_id: str, event: dict) -> dict:
    return {
        "openFloor": {
            "schema": {"version": "1.1", "url": "https://openvoicenetwork.org/schema"},
            "conversation": {"id": conv_id},
            "sender": floor_manager_identity,
            "events": [event],
        }
    }


def deliver_and_collect(conversant, event: dict, floor_manager_identity: dict, conv_id: str, deliver, timeout: float) -> list:
    """Send `event` to one conversant's serviceUrl via the injected
    `deliver` callback; returns whatever event dicts it replied with (an
    empty list on failure -- delivery failures must never abort the round).
    Each reply is stamped with _ORIGIN_KEY: this call is a direct
    request/response against `conversant`, so any events it hands back
    unambiguously originated there, even though the reply itself carries
    no sender/dialogEvent of its own (e.g. a bare acceptInvite)."""
    envelope = _build_outbound_envelope(floor_manager_identity, conv_id, event)
    try:
        events = deliver(conversant.service_url, envelope, timeout) or []
    except Exception:
        return []
    for reply_event in events:
        if isinstance(reply_event, dict):
            reply_event[_ORIGIN_KEY] = conversant.speaker_uri
    return events


def deliver_concurrently(targets: list, event: dict, floor_manager_identity: dict, conv_id: str, deliver, timeout: float) -> list:
    """Deliver `event` to every target concurrently (they're independent
    recipients of the same one event -- the spec's normative
    sequential-processing rule governs the EVENT QUEUE, not fan-out to
    multiple recipients of a single Pass-Through). Results are collected
    and returned in stable target order so downstream queueing stays
    deterministic."""
    if not targets:
        return []
    if len(targets) == 1:
        return deliver_and_collect(targets[0], event, floor_manager_identity, conv_id, deliver, timeout)
    with ThreadPoolExecutor(max_workers=min(MAX_CONCURRENT_DELIVERIES, len(targets))) as pool:
        futures = [
            pool.submit(deliver_and_collect, target, event, floor_manager_identity, conv_id, deliver, timeout)
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
        # (curation rule, section 2.2). This project deliberately reconciles
        # that down to revoked immediately -- see base_strategy_agent.py's
        # _handle_invite for the matching agent-side deviation/rationale.
        conversant.floor_granted = True
        return [{"eventType": REVOKE_FLOOR, "to": {"speakerUri": conversant.speaker_uri, "serviceUrl": conversant.service_url}}]

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
        return []

    if event_type == YIELD_FLOOR:
        conversant = conv.get_conversant(sender_speaker_uri)
        if conversant:
            conversant.floor_granted = False
        return []

    return []


_TRUSTED_KEY = "_floorManagerTrusted"


def process_envelope(conv: ConversationState, in_envelope: dict, floor_manager_identity: dict, deliver, timeout: float = 30.0) -> list:
    """Process every event in in_envelope's "openFloor.events" list per the
    routing table, returning the ordered list of events the caller (browser
    or convener) should be shown/rendered."""
    openfloor = _unwrap_envelope(in_envelope)
    raw_events = openfloor.get("events") or []
    queue = deque(raw_events)
    executed = []

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

        if event_type == UTTERANCE:
            if not trusted and not sender_currently_holds_floor(conv, sender_speaker_uri):
                if conv.convener_speaker_uri:
                    convener_events = delegate_to_convener(conv, event, sender_speaker_uri, floor_manager_identity, deliver, timeout)
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
            elif not is_convener_sender:
                conv.record_turn(sender_speaker_uri, sender_conversant.conversational_name, _extract_utterance_text(event))

            targets = resolve_pass_through_targets(conv, event, sender_speaker_uri)
            reply_events = deliver_concurrently(targets, event, floor_manager_identity, conv.conv_id, deliver, timeout)
            # NOT executed.extend(reply_events) here -- each reply re-enters
            # the SAME table (queue.extend below) and gets appended to
            # `executed` exactly once, when ITS OWN turn through the loop
            # reaches the "executed.append(event)" below. Adding it here too
            # would double-report every specialist reply.
            queue.extend(reply_events)  # each reply re-enters the SAME table, at the tail

            if not trusted and conv.convener_speaker_uri:
                courtesy_events = deliver_courtesy_copy_to_convener(conv, event, sender_speaker_uri, floor_manager_identity, deliver, timeout)
                queue.extendleft(reversed(courtesy_events))

            executed.append(event)
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
            target_is_convener = _event_targets_convener(conv, event)
            if not trusted and conv.convener_speaker_uri and not target_is_convener:
                convener_events = delegate_to_convener(conv, event, sender_speaker_uri, floor_manager_identity, deliver, timeout)
                queue.extendleft(reversed(convener_events))
                continue

            # Trusted (convener-originated), targeting convener itself, or
            # no convener registered: per table, requestFloor -> auto
            # grantFloor; the rest execute as given.
            if event_type == REQUEST_FLOOR:
                resolved = {"eventType": GRANT_FLOOR, "to": event.get("to")}
            else:
                resolved = event
            to = _event_to(resolved)

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

            executed.append(resolved)

            # Pass-Through: the resolved event must actually reach its target
            # conversant -- apply_local_state above only updates the floor
            # manager's OWN bookkeeping; delivery is what flips the agent's
            # own local floor gate (e.g. base_strategy_agent.py's
            # _floor_granted), which is the real point of grantFloor/revokeFloor.
            if target is not None:
                reply_events = deliver_and_collect(target, resolved, floor_manager_identity, conv.conv_id, deliver, timeout)
                # NOT executed.extend(reply_events) -- same reasoning as the
                # utterance branch above: each reply (e.g. an acceptInvite in
                # response to this invite) re-enters the table via
                # queue.extend and gets appended to `executed` exactly once
                # when its own turn through the loop is processed.
                queue.extend(reply_events)

            queue.extend(extra)
            continue

        if event_type in PASS_THROUGH_ALWAYS:
            targets = resolve_pass_through_targets(conv, event, sender_speaker_uri)
            reply_events = deliver_concurrently(targets, event, floor_manager_identity, conv.conv_id, deliver, timeout)
            executed.extend(reply_events)
            apply_local_state(conv, event, sender_speaker_uri)
            if event_type == ACCEPT_INVITE and not conv.convener_speaker_uri:
                accepting_conversant = conv.get_conversant(sender_speaker_uri)
                if accepting_conversant is not None:
                    detect_convener_role(conv, accepting_conversant, floor_manager_identity, deliver, timeout)
            executed.append(event)
            continue

        # Unknown event type: report it unchanged, do nothing else.
        executed.append(event)

    return executed


def detect_convener_role(conv: ConversationState, conversant, floor_manager_identity: dict, deliver, timeout: float) -> bool:
    """Fetch `conversant`'s manifest and register it as this conversation's
    convener if it declares openFloorRoles.convener=true. Called right
    after a conversant accepts its invite (the natural point at which the
    floor manager needs to know whether it just gained a convener),
    without waiting for the convener to be discovered any other way (no
    hardcoded port numbers -- works for any Open-Floor-compliant convener)."""
    envelope = _build_outbound_envelope(floor_manager_identity, conv.conv_id, {"eventType": GET_MANIFESTS})
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


def delegate_to_convener(conv, event, sender_speaker_uri, floor_manager_identity, deliver, timeout):
    return _call_convener(conv, event, sender_speaker_uri, floor_manager_identity, deliver, timeout)


def deliver_courtesy_copy_to_convener(conv, event, sender_speaker_uri, floor_manager_identity, deliver, timeout):
    return _call_convener(conv, event, sender_speaker_uri, floor_manager_identity, deliver, timeout)


def _call_convener(conv, event, sender_speaker_uri, floor_manager_identity, deliver, timeout):
    convener = conv.convener
    if convener is None:
        return []
    envelope = _build_outbound_envelope(floor_manager_identity, conv.conv_id, event)
    openfloor = envelope["openFloor"]
    openfloor["conversation"]["conversants"] = [
        {
            "identification": {
                "speakerUri": c.speaker_uri,
                "serviceUrl": c.service_url,
                "conversationalName": c.conversational_name,
                # organization/synopsis are mandatory (non-Optional) fields
                # on the openfloor package's Identification dataclass --
                # empty strings are structurally valid, and convener only
                # ever reads speakerUri/serviceUrl/conversationalName back
                # out of this list, so no information is actually lost.
                "organization": "",
                "synopsis": "",
            }
        }
        for c in conv.conversants.values()
    ]
    openfloor["conversation"]["floorGranted"] = [c.service_url for c in conv.conversants.values() if c.floor_granted]
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
    try:
        returned_events = deliver(convener.service_url, envelope, timeout) or []
    except Exception:
        return []
    # Trust whatever convener sends back -- it's privileged, per the spec's
    # own wording ("the convener is then responsible for returning this
    # event back to the floor manager OR substituting it with different
    # events"). Marked so process_envelope executes these directly instead
    # of re-delegating them back to convener.
    for returned_event in returned_events:
        if isinstance(returned_event, dict):
            returned_event[_TRUSTED_KEY] = True
    return returned_events
