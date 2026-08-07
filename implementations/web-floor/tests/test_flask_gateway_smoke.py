import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api import flask_gateway


class GatewaySmokeTests(unittest.TestCase):
    """Baseline scaffolding (Phase 0): confirms the existing gateway still
    imports and serves its pre-floor-manager routes. Establishes the test
    runner/pattern before floor-manager logic lands in later phases."""

    def setUp(self):
        self.client = flask_gateway.app.test_client()

    def test_health_route(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "healthy")

    def test_proxy_send_requires_target_url(self):
        response = self.client.post("/api/proxy-send", json={})
        self.assertEqual(response.status_code, 400)

    def test_proxy_stream_requires_target_url(self):
        response = self.client.post("/api/proxy-stream", json={})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
