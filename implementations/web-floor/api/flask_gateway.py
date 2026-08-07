#!/usr/bin/env python3
"""Web-Floor gateway.

A small Flask app that (1) serves the static browser client from ../public and
(2) exposes a single JSON proxy endpoint, POST /api/proxy-send, that forwards
OpenFloor envelopes from the browser to agent services. The proxy exists to get
around browser CORS restrictions and mixed-content limits when the page talks to
many localhost agents. This is the canonical gateway used by the Vercel
entrypoint (index.py); app.py is a thin compatibility shim over it.
"""
import json
import mimetypes
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context

# Fix Windows registry often mapping .js to text/plain
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")


BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR.parent / "public"

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import floor_router
from floor_state import registry as floor_registry

app = Flask(__name__, static_folder=str(PUBLIC_DIR), static_url_path="")

# The floor manager's own Open Floor identity -- used as the `sender` on
# every envelope it originates (delegation calls to convener, courtesy
# copies, and the aggregated response handed back to the caller).
FLOOR_MANAGER_IDENTITY = {
    "speakerUri": os.environ.get("FLOOR_MANAGER_SPEAKER_URI", "tag:web-floor,2026:floor-manager"),
    "serviceUrl": os.environ.get("FLOOR_MANAGER_SERVICE_URL", f"http://127.0.0.1:{os.environ.get('PORT', '8090')}/"),
}


def _parse_csv_env(value: str) -> list[str]:
    # Split a comma-separated env var into a clean list, dropping blanks.
    return [item.strip() for item in (value or "").split(",") if item.strip()]


# Allowed browser origins for CORS; "*" (the default) permits any origin.
CORS_ORIGINS = _parse_csv_env(os.environ.get("CORS_ALLOW_ORIGINS", "*")) or ["*"]
# Optional allowlist of upstream URL prefixes the proxy may forward to (SSRF guard).
TARGET_ALLOWLIST = _parse_csv_env(os.environ.get("GATEWAY_TARGET_ALLOWLIST", ""))

# Absolute ceiling for any single proxied request.
MAX_PROXY_TIMEOUT_SECONDS = 240.0
# Floor applied to utterance requests, which can fan out across many agents.
MIN_UTTERANCE_TIMEOUT_SECONDS = 180.0


def _normalize_timeout_seconds(timeout_ms) -> float:
    # Convert the caller-supplied millisecond timeout to seconds, clamped to a
    # sane range (defaults to 10 s if the value is missing or unparseable).
    try:
        timeout = float(timeout_ms) / 1000.0
    except (TypeError, ValueError):
        timeout = 10.0
    return max(0.1, min(timeout, MAX_PROXY_TIMEOUT_SECONDS))


def _contains_utterance_event(payload: object) -> bool:
    # True if the OpenFloor envelope carries at least one utterance event.
    # Accepts the envelope under any of the historical top-level keys.
    if not isinstance(payload, dict):
        return False
    envelope = payload.get("openFloor") or payload.get("openfloor") or payload.get("ovon") or payload
    if not isinstance(envelope, dict):
        return False
    events = envelope.get("events")
    if not isinstance(events, list):
        return False
    for event in events:
        if isinstance(event, dict) and event.get("eventType") == "utterance":
            return True
    return False


def _effective_timeout_seconds(timeout_ms, payload: object) -> float:
    # Control events use the caller's timeout as-is; utterance events are raised
    # to the long floor because a convener may fan out to many specialists.
    timeout = _normalize_timeout_seconds(timeout_ms)
    # Strategy convener fan-out can exceed 2 minutes under load.
    if _contains_utterance_event(payload):
        return max(timeout, MIN_UTTERANCE_TIMEOUT_SECONDS)
    return timeout


def _is_allowed_target(target_url: str) -> tuple[bool, str]:
    # Validate the proxy target: must be http(s), and (if configured) must match
    # the allowlist. Returns (allowed, reason-if-blocked).
    parsed = urlparse(target_url)
    if parsed.scheme not in ("http", "https"):
        return False, "targetUrl must use http:// or https://"

    # SSRF guard: when GATEWAY_TARGET_ALLOWLIST is unset the gateway will proxy
    # to ANY http(s) URL a client supplies. That is fine for local development,
    # but for any shared/public deployment set GATEWAY_TARGET_ALLOWLIST to a
    # comma-separated list of allowed URL prefixes to avoid an open proxy.
    if TARGET_ALLOWLIST and not any(target_url.startswith(prefix) for prefix in TARGET_ALLOWLIST):
        return False, "targetUrl is not in GATEWAY_TARGET_ALLOWLIST"

    return True, ""


@app.after_request
def _add_cors_headers(response):
    # Attach CORS headers to every response so the browser client (possibly on a
    # different origin) can call the proxy. Echoes a specific origin when an
    # explicit allowlist is configured, otherwise allows all.
    origin = request.headers.get("Origin", "")
    if CORS_ORIGINS == ["*"]:
        response.headers["Access-Control-Allow-Origin"] = "*"
    elif origin and origin in CORS_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"

    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/api/proxy-send", methods=["OPTIONS"])
def proxy_send_options():
    # CORS preflight for the proxy endpoint.
    return ("", 204)


@app.route("/api/proxy-send", methods=["POST"])
def proxy_send():
    # Core proxy: take {targetUrl, payload, timeoutMs} from the browser, POST
    # the payload to the target agent, and relay a normalized result back.
    body = request.get_json(silent=True) or {}
    target_url = body.get("targetUrl")
    payload = body.get("payload") or {}
    # Let _effective_timeout_seconds decide: control events use the caller's
    # timeout; only utterance events are raised to the long fan-out floor.
    timeout_seconds = _effective_timeout_seconds(body.get("timeoutMs", 10000), payload)

    if not isinstance(target_url, str) or not target_url.strip():
        return jsonify({"error": "targetUrl is required"}), 400

    target_url = target_url.strip()
    allowed, reason = _is_allowed_target(target_url)
    if not allowed:
        return jsonify(
            {
                "ok": False,
                "status": 0,
                "statusText": "BLOCKED_TARGET",
                "error": reason,
            }
        ), 200

    outbound_body = json.dumps(payload).encode("utf-8")
    # Forward the envelope verbatim to the agent as a POST with JSON headers.
    outbound = Request(
        target_url,
        data=outbound_body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "web-floor-flask-gateway/0.1",
        },
    )

    try:
        with urlopen(outbound, timeout=timeout_seconds) as response:
            raw_text = response.read().decode("utf-8", errors="replace")
            status = response.getcode()
            status_text = getattr(response, "reason", "") or ""
    except HTTPError as error:
        # HTTP error status (4xx/5xx): still relay the body/status to the client.
        raw_text = error.read().decode("utf-8", errors="replace")
        status = error.code
        status_text = error.reason or ""
    except URLError as error:
        # Connection-level failure (host down, DNS, timeout): report as a soft
        # 200 with ok=False so the browser can surface it without a fetch reject.
        return jsonify(
            {
                "ok": False,
                "status": 0,
                "statusText": "REQUEST_ERROR",
                "error": str(error.reason),
            }
        ), 200
    except Exception as error:
        return jsonify(
            {
                "ok": False,
                "status": 0,
                "statusText": "REQUEST_ERROR",
                "error": str(error),
            }
        ), 200

    # Parse the agent's body as JSON when possible; pass raw text through too.
    try:
        parsed_json = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed_json = None

    # Uniform envelope the browser client expects: ok flag + status + both the
    # raw text and parsed JSON of the upstream response.
    return jsonify(
        {
            "ok": 200 <= status < 300,
            "status": status,
            "statusText": status_text,
            "text": raw_text,
            "json": parsed_json,
        }
    ), 200


@app.route("/api/proxy-stream", methods=["OPTIONS"])
def proxy_stream_options():
    # CORS preflight for the streaming proxy endpoint.
    return ("", 204)


@app.route("/api/proxy-stream", methods=["POST"])
def proxy_stream():
    # Streaming counterpart to /api/proxy-send: relays the upstream response to
    # the browser as bytes arrive instead of buffering the whole body first.
    # Used for round-robin conversations, where the convener flushes each
    # specialist's answer (one newline-delimited JSON envelope) as soon as
    # that specialist's turn completes, so the UI can render turns as they
    # happen instead of waiting for the entire round to finish.
    body = request.get_json(silent=True) or {}
    target_url = body.get("targetUrl")
    payload = body.get("payload") or {}
    timeout_seconds = _effective_timeout_seconds(body.get("timeoutMs", 10000), payload)

    if not isinstance(target_url, str) or not target_url.strip():
        return jsonify({"error": "targetUrl is required"}), 400

    target_url = target_url.strip()
    allowed, reason = _is_allowed_target(target_url)
    if not allowed:
        return jsonify(
            {
                "ok": False,
                "status": 0,
                "statusText": "BLOCKED_TARGET",
                "error": reason,
            }
        ), 200

    outbound_body = json.dumps(payload).encode("utf-8")
    outbound = Request(
        target_url,
        data=outbound_body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/x-ndjson",
            "User-Agent": "web-floor-flask-gateway/0.1",
        },
    )

    def relay():
        # Read the upstream in small chunks and yield each one immediately;
        # urlopen's timeout applies per blocking read, not to the whole
        # streamed duration, so a slow-but-steady stream won't be cut off.
        #
        # Deliberately read1(), not read(): for a chunked-transfer-encoded
        # response, HTTPResponse.read(n) tries to fill the full n bytes by
        # pulling from as many upstream chunks as it takes, which can block
        # until the entire stream finishes if the total body is smaller than
        # n. read1(n) returns after a single underlying read instead, which
        # is what actually gets each specialist's turn relayed to the browser
        # as soon as it arrives rather than all at once at the end.
        try:
            with urlopen(outbound, timeout=timeout_seconds) as upstream:
                while True:
                    chunk = upstream.read1(65536)
                    if not chunk:
                        break
                    yield chunk
        except HTTPError as error:
            yield error.read()
        except URLError as error:
            yield (json.dumps({"error": str(error.reason)}) + "\n").encode("utf-8")
        except Exception as error:
            yield (json.dumps({"error": str(error)}) + "\n").encode("utf-8")

    return Response(stream_with_context(relay()), mimetype="application/x-ndjson")


def _deliver_via_http(target_url: str, envelope: dict, timeout: float) -> list:
    """Real HTTP-backed delivery used by the floor manager (floor_router.py)
    to actually reach a conversant's serviceUrl. Mirrors /api/proxy-send's
    request-building and SSRF allowlist, but returns the parsed list of
    reply events directly instead of a wrapped proxy response, since this
    is called internally by floor_router's routing loop, not by a browser."""
    allowed, _reason = _is_allowed_target(target_url)
    if not allowed:
        return []
    outbound_body = json.dumps(envelope).encode("utf-8")
    outbound = Request(
        target_url,
        data=outbound_body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "web-floor-flask-gateway/0.1",
        },
    )
    try:
        with urlopen(outbound, timeout=timeout) as response:
            raw_text = response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, Exception):
        return []
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return []
    openfloor = parsed.get("openFloor") or parsed.get("openfloor") or parsed.get("ovon") or parsed
    events = openfloor.get("events") if isinstance(openfloor, dict) else None
    return events if isinstance(events, list) else []


def _conversation_id(payload: dict) -> str:
    openfloor = payload.get("openFloor") or payload.get("openfloor") or payload.get("ovon") or payload
    conversation = openfloor.get("conversation") if isinstance(openfloor, dict) else None
    conv_id = conversation.get("id") if isinstance(conversation, dict) else None
    return conv_id or "default"


def _build_response_envelope(conv_id: str, executed_events: list) -> dict:
    return {
        "openFloor": {
            "schema": {"version": "1.1", "url": "https://openvoicenetwork.org/schema"},
            "conversation": {"id": conv_id},
            "sender": FLOOR_MANAGER_IDENTITY,
            "events": executed_events,
        }
    }


@app.route("/api/floor/send", methods=["OPTIONS"])
def floor_send_options():
    # CORS preflight for the floor-managed send endpoint.
    return ("", 204)


@app.route("/api/floor/send", methods=["POST"])
def floor_send():
    # Floor-managed counterpart to /api/proxy-send: no targetUrl -- targets
    # are derived entirely from each event's `to` field plus the floor
    # manager's own conversant/routing decisions (floor_router.py).
    body = request.get_json(silent=True) or {}
    payload = body.get("payload") or {}
    timeout_seconds = _effective_timeout_seconds(body.get("timeoutMs", 10000), payload)

    conv_id = _conversation_id(payload)
    conv = floor_registry.get_or_create(conv_id)
    with conv.lock:
        executed = floor_router.process_envelope(conv, payload, FLOOR_MANAGER_IDENTITY, _deliver_via_http, timeout_seconds)

    return jsonify(_build_response_envelope(conv_id, executed)), 200


@app.route("/api/floor/stream", methods=["OPTIONS"])
def floor_stream_options():
    # CORS preflight for the floor-managed streaming endpoint.
    return ("", 204)


@app.route("/api/floor/stream", methods=["POST"])
def floor_stream():
    # NDJSON counterpart to /api/floor/send. Phase 1 note: this runs the
    # full exchange synchronously and yields one aggregated envelope --
    # true per-turn incremental flushing (matching the old
    # /round-robin-stream's one-line-per-turn behavior) needs a
    # generator-based floor_router.process_envelope, which lands with the
    # round-robin decision loop in Phase 3. Kept as a real NDJSON response
    # now (not a stub) so app.js's cutover in Phase 4 doesn't need to
    # distinguish "streaming not implemented yet" as a separate case.
    body = request.get_json(silent=True) or {}
    payload = body.get("payload") or {}
    timeout_seconds = _effective_timeout_seconds(body.get("timeoutMs", 10000), payload)
    conv_id = _conversation_id(payload)

    def generate():
        conv = floor_registry.get_or_create(conv_id)
        with conv.lock:
            executed = floor_router.process_envelope(conv, payload, FLOOR_MANAGER_IDENTITY, _deliver_via_http, timeout_seconds)
        yield (json.dumps(_build_response_envelope(conv_id, executed)) + "\n").encode("utf-8")

    return Response(stream_with_context(generate()), mimetype="application/x-ndjson")


@app.route("/api/floor/state", methods=["GET"])
def floor_state_snapshot():
    # Read-only conversant/floor-state snapshot, for UI resync.
    conv_id = request.args.get("conversationId") or "default"
    conv = floor_registry.get(conv_id)
    conversants = [] if conv is None else [
        {
            "serviceUrl": c.service_url,
            "speakerUri": c.speaker_uri,
            "conversationalName": c.conversational_name,
            "floorGranted": c.floor_granted,
            "isConvener": c.is_convener,
        }
        for c in conv.conversants.values()
    ]
    return jsonify({"conversationId": conv_id, "conversants": conversants}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify(
        {
            "status": "healthy",
            "service": "web-floor-flask-gateway",
            "port": int(os.environ.get("PORT", "8090")),
        }
    )


@app.route("/", methods=["GET"])
def index():
    # Serve the SPA entry point. No-cache headers ensure the browser always
    # picks up the latest client during active development.
    response = send_from_directory(PUBLIC_DIR, "index.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/<path:asset_path>", methods=["GET"])
def serve_static(asset_path: str):
    # Serve a real static asset when it exists; otherwise fall back to
    # index.html so client-side routes resolve. All responses are no-cache.
    candidate = PUBLIC_DIR / asset_path
    if candidate.exists() and candidate.is_file():
        response = send_from_directory(PUBLIC_DIR, asset_path)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    response = send_from_directory(PUBLIC_DIR, "index.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8090"))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    app.run(host=host, port=port, debug=debug)
