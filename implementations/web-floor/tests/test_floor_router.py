import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
API_DIR = ROOT / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

import floor_router as router
from floor_state import ConversationState


FLOOR_MANAGER_IDENTITY = {"speakerUri": "tag:web-floor,2026:manager", "serviceUrl": "http://localhost:8090/"}


def utterance_event(text, speaker_uri, to=None, private=False):
    event = {
        "eventType": "utterance",
        "parameters": {"dialogEvent": {"speakerUri": speaker_uri, "features": {"text": {"tokens": [{"value": text}]}}}},
    }
    if to is not None:
        event["to"] = {**to, "private": private} if private else to
    return event


def envelope(sender_speaker_uri, events):
    return {"openFloor": {"conversation": {"id": "conv-1"}, "sender": {"speakerUri": sender_speaker_uri}, "events": events}}


class FakeDeliver:
    """Records every call and returns a scripted reply per target URL."""

    def __init__(self, replies=None):
        self.replies = replies or {}
        self.calls = []
        self._lock = threading.Lock()

    def __call__(self, target_url, sent_envelope, timeout):
        with self._lock:
            self.calls.append((target_url, sent_envelope))
        return self.replies.get(target_url, [])


class NoConvenerUtteranceTests(unittest.TestCase):
    def setUp(self):
        self.conv = ConversationState(conv_id="conv-1")
        self.conv.add_conversant("tag:market", "http://localhost:8200/", "Market Validator")
        self.conv.add_conversant("tag:skeptic", "http://localhost:8206/", "Devil's Advocate")
        # Real usage always reconciles floor_granted down to False right
        # after invite (the router's auto-revoke, per the project's
        # documented deviation) -- match that steady state here instead of
        # the spec-literal True the raw dataclass defaults to, so these
        # tests reflect what a real post-invite conversant actually looks
        # like. Individual tests override this explicitly where relevant.
        self.conv.get_conversant("tag:market").floor_granted = False
        self.conv.get_conversant("tag:skeptic").floor_granted = False

    def test_utterance_from_human_pass_throughs_to_all_conversants(self):
        deliver = FakeDeliver()
        in_env = envelope("tag:human", [utterance_event("evaluate this idea", "tag:human")])

        router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        called_urls = {url for url, _ in deliver.calls}
        self.assertEqual(called_urls, {"http://localhost:8200/", "http://localhost:8206/"})

    def test_utterance_from_non_floor_holder_is_ignored(self):
        # Neither conversant currently holds the floor (default state after
        # setUp's add_conversant calls, before any grant).
        self.conv.get_conversant("tag:market").floor_granted = False
        deliver = FakeDeliver()
        in_env = envelope("tag:market", [utterance_event("I have thoughts", "tag:market")])

        router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        self.assertEqual(deliver.calls, [])

    def test_utterance_from_floor_holder_is_delivered(self):
        self.conv.get_conversant("tag:market").floor_granted = True
        deliver = FakeDeliver()
        in_env = envelope("tag:market", [utterance_event("TAM is $1B", "tag:market")])

        router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        # Delivered to the OTHER conversant, never back to the sender itself.
        called_urls = {url for url, _ in deliver.calls}
        self.assertEqual(called_urls, {"http://localhost:8206/"})

    def test_private_utterance_narrows_to_one_recipient(self):
        deliver = FakeDeliver()
        in_env = envelope(
            "tag:human",
            [utterance_event("psst", "tag:human", to={"speakerUri": "tag:market"}, private=True)],
        )

        router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        called_urls = {url for url, _ in deliver.calls}
        self.assertEqual(called_urls, {"http://localhost:8200/"})

    def test_reply_from_floor_holder_is_reprocessed_and_broadcast_onward(self):
        # market still holds the floor when it replies (nothing in the
        # no-convener path auto-revokes after speaking -- that's a
        # convener decision, out of Phase 1 scope), so per the table its
        # reply utterance is itself Pass-Through too. skeptic therefore
        # receives TWO deliveries: the original human broadcast, and a
        # second one from market's reply being reprocessed and rebroadcast.
        deliver = FakeDeliver(replies={
            "http://localhost:8200/": [utterance_event("my analysis", "tag:market")],
        })
        self.conv.get_conversant("tag:market").floor_granted = True
        in_env = envelope("tag:human", [utterance_event("go", "tag:human")])

        executed = router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        skeptic_calls = [c for c in deliver.calls if c[0] == "http://localhost:8206/"]
        self.assertEqual(len(skeptic_calls), 2)
        self.assertIn(utterance_event("my analysis", "tag:market")["parameters"], [e.get("parameters") for e in executed])

    def test_reply_from_a_speaker_revoked_mid_turn_is_ignored_not_broadcast(self):
        # market is granted the floor, gets the broadcast, and its reply
        # comes back -- but its floor was revoked as a side effect of
        # answering (exactly what a convener decision will do starting in
        # Phase 3). By the time that reply re-enters the table, market no
        # longer holds the floor, so its reply must be Ignored: skeptic
        # gets only the ONE delivery from the original human broadcast,
        # not a second one from market's (now-ignored) reply.
        self.conv.get_conversant("tag:market").floor_granted = True
        calls = []

        def deliver_and_revoke(target_url, sent_envelope, timeout):
            calls.append(target_url)
            if target_url == "http://localhost:8200/":
                self.conv.get_conversant("tag:market").floor_granted = False
                return [utterance_event("my analysis", "tag:market")]
            return []

        in_env = envelope("tag:human", [utterance_event("go", "tag:human")])
        router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver_and_revoke)

        self.assertEqual(calls.count("http://localhost:8200/"), 1)
        self.assertEqual(calls.count("http://localhost:8206/"), 1)

    def test_concurrent_delivery_reaches_all_targets(self):
        self.conv.add_conversant("tag:funding", "http://localhost:8204/", "Funding Strategist")
        deliver = FakeDeliver()
        in_env = envelope("tag:human", [utterance_event("go", "tag:human")])

        router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        called_urls = {url for url, _ in deliver.calls}
        self.assertEqual(called_urls, {"http://localhost:8200/", "http://localhost:8206/", "http://localhost:8204/"})


class NoConvenerControlEventTests(unittest.TestCase):
    def setUp(self):
        self.conv = ConversationState(conv_id="conv-1")

    def test_invite_adds_conversant_then_auto_revokes(self):
        deliver = FakeDeliver()
        in_env = envelope(
            "tag:human",
            [{"eventType": "invite", "to": {"speakerUri": "tag:market", "serviceUrl": "http://localhost:8200/"}}],
        )

        router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        conversant = self.conv.get_conversant("tag:market")
        self.assertIsNotNone(conversant)
        self.assertFalse(conversant.floor_granted)  # reconciled down per project deviation

    def test_invite_is_delivered_to_the_invitee(self):
        deliver = FakeDeliver()
        in_env = envelope(
            "tag:human",
            [{"eventType": "invite", "to": {"speakerUri": "tag:market", "serviceUrl": "http://localhost:8200/"}}],
        )

        router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        called_urls = {url for url, _ in deliver.calls}
        self.assertIn("http://localhost:8200/", called_urls)

    def test_uninvite_removes_conversant(self):
        self.conv.add_conversant("tag:market", "http://localhost:8200/")
        deliver = FakeDeliver()
        in_env = envelope(
            "tag:human",
            [{"eventType": "uninvite", "to": {"speakerUri": "tag:market", "serviceUrl": "http://localhost:8200/"}}],
        )

        router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        self.assertIsNone(self.conv.get_conversant("tag:market"))

    def test_request_floor_auto_grants(self):
        self.conv.add_conversant("tag:market", "http://localhost:8200/")
        deliver = FakeDeliver()
        in_env = envelope(
            "tag:market",
            [{"eventType": "requestFloor", "to": {"speakerUri": "tag:market", "serviceUrl": "http://localhost:8200/"}}],
        )

        executed = router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        self.assertTrue(self.conv.get_conversant("tag:market").floor_granted)
        self.assertTrue(any(e.get("eventType") == "grantFloor" for e in executed))

    def test_grant_and_revoke_floor_update_state(self):
        self.conv.add_conversant("tag:market", "http://localhost:8200/")
        deliver = FakeDeliver()

        router.process_envelope(
            self.conv,
            envelope("tag:human", [{"eventType": "grantFloor", "to": {"speakerUri": "tag:market", "serviceUrl": "http://localhost:8200/"}}]),
            FLOOR_MANAGER_IDENTITY, deliver,
        )
        self.assertTrue(self.conv.get_conversant("tag:market").floor_granted)

        router.process_envelope(
            self.conv,
            envelope("tag:human", [{"eventType": "revokeFloor", "to": {"speakerUri": "tag:market", "serviceUrl": "http://localhost:8200/"}}]),
            FLOOR_MANAGER_IDENTITY, deliver,
        )
        self.assertFalse(self.conv.get_conversant("tag:market").floor_granted)

    def test_accept_invite_marks_accepted(self):
        self.conv.add_conversant("tag:market", "http://localhost:8200/")
        deliver = FakeDeliver()
        in_env = envelope("tag:market", [{"eventType": "acceptInvite"}])

        router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        self.assertTrue(self.conv.get_conversant("tag:market").accepted)

    def test_decline_invite_removes_conversant(self):
        self.conv.add_conversant("tag:market", "http://localhost:8200/")
        deliver = FakeDeliver()
        in_env = envelope("tag:market", [{"eventType": "declineInvite"}])

        router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        self.assertIsNone(self.conv.get_conversant("tag:market"))

    def test_bye_removes_conversant(self):
        self.conv.add_conversant("tag:market", "http://localhost:8200/")
        deliver = FakeDeliver()
        in_env = envelope("tag:market", [{"eventType": "bye"}])

        router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        self.assertIsNone(self.conv.get_conversant("tag:market"))


def publish_manifests_reply(is_convener):
    return [{
        "eventType": "publishManifests",
        "parameters": {
            "servicingManifests": [
                {"identification": {"speakerUri": "tag:convener", "serviceUrl": "http://localhost:8199/", "openFloorRoles": {"convener": is_convener}}}
            ],
            "discoveryManifests": [],
        },
    }]


class ConvenerDetectionTests(unittest.TestCase):
    """Auto-detection is manifest-based (openFloorRoles.convener), not a
    hardcoded port -- fires when a conversant accepts its invite."""

    def setUp(self):
        self.conv = ConversationState(conv_id="conv-1")
        self.conv.add_conversant("tag:convener", "http://localhost:8199/", "Convener")

    def test_accept_invite_from_a_convener_registers_it(self):
        deliver = FakeDeliver(replies={"http://localhost:8199/": publish_manifests_reply(is_convener=True)})
        in_env = envelope("tag:convener", [{"eventType": "acceptInvite"}])

        router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        self.assertEqual(self.conv.convener_speaker_uri, "tag:convener")
        self.assertTrue(self.conv.get_conversant("tag:convener").is_convener)

    def test_accept_invite_from_a_non_convener_does_not_register(self):
        self.conv.add_conversant("tag:market", "http://localhost:8200/", "Market Validator")
        deliver = FakeDeliver(replies={"http://localhost:8200/": publish_manifests_reply(is_convener=False)})
        in_env = envelope("tag:market", [{"eventType": "acceptInvite"}])

        router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        self.assertIsNone(self.conv.convener_speaker_uri)
        self.assertFalse(self.conv.get_conversant("tag:market").is_convener)

    def test_detection_is_skipped_once_a_convener_is_already_registered(self):
        self.conv.convener_speaker_uri = "tag:convener"
        self.conv.get_conversant("tag:convener").is_convener = True
        self.conv.add_conversant("tag:market", "http://localhost:8200/", "Market Validator")
        deliver = FakeDeliver(replies={"http://localhost:8200/": publish_manifests_reply(is_convener=False)})
        in_env = envelope("tag:market", [{"eventType": "acceptInvite"}])

        router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        # No getManifests probe should even have been sent to market, since
        # a convener is already registered for this conversation.
        market_calls = [c for c in deliver.calls if c[0] == "http://localhost:8200/"]
        self.assertEqual(market_calls, [])

    def test_detected_when_acceptinvite_arrives_as_a_reply_to_our_own_invite(self):
        # Real-world shape (unlike the tests above, which hand acceptInvite
        # straight in as a top-level event): the HUMAN sends an `invite`,
        # convener's acceptInvite comes back nested as a reply via
        # deliver_and_collect with no sender/dialogEvent of its own, and the
        # original envelope's sender is the human throughout. Detection must
        # still attribute that reply to convener, not to the human --
        # regression test for the missing-_ORIGIN_KEY bug where
        # resolve_sender_speaker_uri fell back to the envelope-level sender
        # for any event without its own sender info.
        self.conv = ConversationState(conv_id="conv-1")  # no pre-added convener conversant this time

        def deliver(target_url, sent_envelope, timeout):
            sent_events = sent_envelope["openFloor"]["events"]
            event_type = sent_events[0]["eventType"]
            if target_url != "http://localhost:8199/":
                return []
            if event_type == "invite":
                return [{"eventType": "acceptInvite"}]
            if event_type == "getManifests":
                return publish_manifests_reply(is_convener=True)
            return []

        in_env = envelope(
            "tag:human",
            [{"eventType": "invite", "to": {"speakerUri": "tag:convener", "serviceUrl": "http://localhost:8199/"}}],
        )

        router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        self.assertEqual(self.conv.convener_speaker_uri, "tag:convener")
        self.assertTrue(self.conv.get_conversant("tag:convener").is_convener)
        self.assertTrue(self.conv.get_conversant("tag:convener").accepted)

    def test_inviting_the_convener_does_not_infinite_loop_on_its_own_auto_revoke(self):
        # apply_local_state's invite handling always queues a REVOKE_FLOOR
        # for the newly-added conversant -- including when that conversant
        # IS the convener. Once convener registration lands mid-loop (right
        # after its acceptInvite is processed), that pending revokeFloor(to
        # =convener) must NOT be delegated to convener: a real (mocked
        # here) convener trivially echoes a delegated control event back
        # unchanged, roundHistory parameters and all: if the router then
        # delivered that "approved" event to its target -- convener again
        # -- convener would see the same roundHistory marker and treat the
        # delivery as a brand-new delegation request, echoing forever.
        # Regression test for exactly that hang.
        self.conv = ConversationState(conv_id="conv-1")
        calls = {"count": 0}

        def deliver(target_url, sent_envelope, timeout):
            calls["count"] += 1
            self.assertLess(calls["count"], 20, "runaway delegate/deliver ping-pong to convener")
            sent_event = sent_envelope["openFloor"]["events"][0]
            event_type = sent_event["eventType"]
            if target_url != "http://localhost:8199/":
                return []
            if event_type == "invite":
                return [{"eventType": "acceptInvite"}]
            if event_type == "getManifests":
                return publish_manifests_reply(is_convener=True)
            if "roundHistory" in (sent_event.get("parameters") or {}):
                # Trivial echo, exactly like convener.py's real delegated
                # control-event handling.
                return [sent_event]
            return []

        in_env = envelope(
            "tag:human",
            [{"eventType": "invite", "to": {"speakerUri": "tag:convener", "serviceUrl": "http://localhost:8199/"}}],
        )

        executed = router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        self.assertTrue(self.conv.get_conversant("tag:convener").is_convener)
        self.assertFalse(self.conv.get_conversant("tag:convener").floor_granted)
        revoke_events = [e for e in executed if e.get("eventType") == "revokeFloor"]
        self.assertEqual(len(revoke_events), 1)


class ConvenerPresentTests(unittest.TestCase):
    """Convener detection itself lands in Phase 2, but the router already
    supports the convener-present column -- test it directly by setting
    conv.convener_speaker_uri, so no rewrite is needed later."""

    def setUp(self):
        self.conv = ConversationState(conv_id="conv-1")
        self.conv.add_conversant("tag:convener", "http://localhost:8199/", "Convener")
        self.conv.convener_speaker_uri = "tag:convener"
        self.conv.add_conversant("tag:market", "http://localhost:8200/", "Market Validator")
        self.conv.get_conversant("tag:market").floor_granted = True

    def test_grant_floor_is_delegated_not_applied_directly(self):
        deliver = FakeDeliver()  # convener returns nothing -> no-op
        in_env = envelope(
            "tag:human",
            [{"eventType": "grantFloor", "to": {"speakerUri": "tag:skeptic", "serviceUrl": "http://localhost:8206/"}}],
        )

        router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        called_urls = {url for url, _ in deliver.calls}
        self.assertEqual(called_urls, {"http://localhost:8199/"})  # went to convener, not applied/delivered directly

    def test_convener_returned_events_are_executed(self):
        deliver = FakeDeliver(replies={
            "http://localhost:8199/": [{"eventType": "revokeFloor", "to": {"speakerUri": "tag:market", "serviceUrl": "http://localhost:8200/"}}],
        })
        in_env = envelope(
            "tag:human",
            [{"eventType": "grantFloor", "to": {"speakerUri": "tag:market", "serviceUrl": "http://localhost:8200/"}}],
        )

        router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        self.assertFalse(self.conv.get_conversant("tag:market").floor_granted)

    def test_utterance_gets_courtesy_copied_to_convener(self):
        deliver = FakeDeliver()
        in_env = envelope("tag:human", [utterance_event("evaluate this idea", "tag:human")])

        router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        called_urls = {url for url, _ in deliver.calls}
        self.assertIn("http://localhost:8199/", called_urls)

    def test_convener_courtesy_copy_receives_conversant_roster_and_round_context(self):
        # A fresh human utterance captures the question and starts the round
        # (clearing any prior round_history, since it's a NEW question).
        deliver = FakeDeliver()
        in_env = envelope("tag:human", [utterance_event("what about risk?", "tag:human")])

        router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        convener_calls = [c for c in deliver.calls if c[0] == "http://localhost:8199/"]
        self.assertTrue(convener_calls)
        sent_event = convener_calls[0][1]["openFloor"]["events"][0]
        self.assertEqual(sent_event["parameters"]["roundHistory"], [])
        self.assertEqual(sent_event["parameters"]["roundQuestion"], "what about risk?")
        conversants = convener_calls[0][1]["openFloor"]["conversation"]["conversants"]
        self.assertTrue(any(c["identification"]["speakerUri"] == "tag:market" for c in conversants))

    def test_specialist_reply_is_recorded_and_seen_by_convener_on_its_own_courtesy_copy(self):
        # market replies while holding the floor; by the time ITS reply is
        # reprocessed and courtesy-copied to convener, convener should see
        # itself already reflected in roundHistory/roundTurnOrder.
        self.conv.get_conversant("tag:market").floor_granted = True
        deliver = FakeDeliver(replies={
            "http://localhost:8200/": [utterance_event("TAM is $1B", "tag:market")],
        })
        in_env = envelope("tag:human", [utterance_event("what about risk?", "tag:human")])

        router.process_envelope(self.conv, in_env, FLOOR_MANAGER_IDENTITY, deliver)

        convener_calls = [c for c in deliver.calls if c[0] == "http://localhost:8199/"]
        # Second courtesy copy (for market's reply) should carry the recorded turn.
        self.assertGreaterEqual(len(convener_calls), 2)
        second_call_params = convener_calls[1][1]["openFloor"]["events"][0]["parameters"]
        self.assertEqual(second_call_params["roundHistory"][0]["text"], "TAM is $1B")
        self.assertIn("tag:market", second_call_params["roundTurnOrder"])
        self.assertEqual(second_call_params["roundQuestion"], "what about risk?")


if __name__ == "__main__":
    unittest.main()
