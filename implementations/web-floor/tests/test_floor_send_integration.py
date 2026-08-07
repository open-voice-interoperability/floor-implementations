import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
API_DIR = ROOT / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from flask import Flask, jsonify, request

from api import flask_gateway


def _extract_text(event):
    dialog = (event.get("parameters") or {}).get("dialogEvent") or {}
    tokens = (dialog.get("features") or {}).get("text", {}).get("tokens") or []
    return tokens[0].get("value", "") if tokens else ""


def make_fake_agent(agent_name, speaker_uri, service_url):
    """A minimal fake specialist: accepts invites, tracks its own floor
    state locally (mirroring base_strategy_agent.py's real behavior), and
    only replies to an utterance while it holds the floor."""
    fake_app = Flask(agent_name)
    state = {"floor_granted": False}

    @fake_app.route("/", methods=["POST"])
    def handle():
        body = request.get_json(silent=True) or {}
        openfloor = body.get("openFloor") or {}
        events = openfloor.get("events") or []
        out_events = []
        for event in events:
            event_type = event.get("eventType")
            if event_type == "invite":
                out_events.append({"eventType": "acceptInvite"})
            elif event_type == "grantFloor":
                state["floor_granted"] = True
            elif event_type == "revokeFloor":
                state["floor_granted"] = False
            elif event_type == "utterance" and state["floor_granted"]:
                text = _extract_text(event)
                out_events.append({
                    "eventType": "utterance",
                    "parameters": {
                        "dialogEvent": {
                            "speakerUri": speaker_uri,
                            "features": {"text": {"tokens": [{"value": f"{agent_name} says: {text}"}]}},
                        }
                    },
                })
        return jsonify({
            "openFloor": {
                "conversation": {},
                "sender": {"speakerUri": speaker_uri, "serviceUrl": service_url},
                "events": out_events,
            }
        })

    return fake_app, state


class FloorSendIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.gateway_client = flask_gateway.app.test_client()

        self.market_app, self.market_state = make_fake_agent(
            "market", "tag:market", "http://localhost:8200/"
        )
        self.market_client = self.market_app.test_client()

        self.skeptic_app, self.skeptic_state = make_fake_agent(
            "skeptic", "tag:skeptic", "http://localhost:8206/"
        )
        self.skeptic_client = self.skeptic_app.test_client()

        def fake_deliver(target_url, envelope, timeout):
            client = {
                "http://localhost:8200/": self.market_client,
                "http://localhost:8206/": self.skeptic_client,
            }.get(target_url)
            if client is None:
                return []
            response = client.post("/", json=envelope)
            body = response.get_json(silent=True) or {}
            openfloor = body.get("openFloor") or {}
            return openfloor.get("events") or []

        self.deliver_patcher = patch.object(flask_gateway, "_deliver_via_http", side_effect=fake_deliver)
        self.deliver_patcher.start()
        # floor_router's process_envelope receives the deliver callback as a
        # parameter from flask_gateway's route handlers -- patching the
        # attribute flask_gateway reads it from is what actually takes effect.
        self.addCleanup(self.deliver_patcher.stop)

    def _send(self, conv_id, sender_speaker_uri, events):
        payload = {
            "openFloor": {
                "conversation": {"id": conv_id},
                "sender": {"speakerUri": sender_speaker_uri},
                "events": events,
            }
        }
        response = self.gateway_client.post("/api/floor/send", json={"payload": payload})
        self.assertEqual(response.status_code, 200)
        return response.get_json()["openFloor"]["events"]

    def test_invite_then_grant_then_utterance_round_trip(self):
        conv_id = "integration-conv-1"

        self._send(conv_id, "tag:human", [
            {"eventType": "invite", "to": {"speakerUri": "tag:market", "serviceUrl": "http://localhost:8200/"}},
        ])
        conv = flask_gateway.floor_registry.get(conv_id)
        self.assertIsNotNone(conv.get_conversant("tag:market"))
        self.assertFalse(conv.get_conversant("tag:market").floor_granted)  # auto-revoked after invite

        self._send(conv_id, "tag:human", [
            {"eventType": "grantFloor", "to": {"speakerUri": "tag:market", "serviceUrl": "http://localhost:8200/"}},
        ])
        self.assertTrue(conv.get_conversant("tag:market").floor_granted)

        events = self._send(conv_id, "tag:human", [
            {
                "eventType": "utterance",
                "parameters": {"dialogEvent": {"speakerUri": "tag:human", "features": {"text": {"tokens": [{"value": "what's the TAM?"}]}}}},
            },
        ])
        reply_texts = [_extract_text(e) for e in events if e.get("eventType") == "utterance"]
        self.assertIn("market says: what's the TAM?", reply_texts)

    def test_ungranted_agent_does_not_reply(self):
        conv_id = "integration-conv-2"
        self._send(conv_id, "tag:human", [
            {"eventType": "invite", "to": {"speakerUri": "tag:skeptic", "serviceUrl": "http://localhost:8206/"}},
        ])
        # No grantFloor sent -- skeptic stays revoked.

        events = self._send(conv_id, "tag:human", [
            {
                "eventType": "utterance",
                "parameters": {"dialogEvent": {"speakerUri": "tag:human", "features": {"text": {"tokens": [{"value": "hello?"}]}}}},
            },
        ])
        reply_texts = [_extract_text(e) for e in events if e.get("eventType") == "utterance"]
        self.assertNotIn("skeptic says: hello?", reply_texts)

    def test_floor_state_snapshot_reflects_conversants(self):
        conv_id = "integration-conv-3"
        self._send(conv_id, "tag:human", [
            {"eventType": "invite", "to": {"speakerUri": "tag:market", "serviceUrl": "http://localhost:8200/"}},
        ])

        response = self.gateway_client.get(f"/api/floor/state?conversationId={conv_id}")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["conversationId"], conv_id)
        speaker_uris = [c["speakerUri"] for c in body["conversants"]]
        self.assertIn("tag:market", speaker_uris)


if __name__ == "__main__":
    unittest.main()
