from flask import Flask, request, jsonify, send_from_directory
import os
import glob
@app.route("/debug-files", methods=["GET"])
def debug_files():
    files = []
    try:
        for root, dirs, filenames in os.walk(PUBLIC_DIR):
            for filename in filenames:
                rel_path = os.path.relpath(os.path.join(root, filename), PUBLIC_DIR)
                files.append(rel_path)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"files": files})
#!/usr/bin/env python3
import json
import mimetypes
import os
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from flask import Flask, request, jsonify, send_from_directory

# Fix Windows registry often mapping .js to text/plain
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR.parent / "public"

app = Flask(__name__, static_folder=str(PUBLIC_DIR), static_url_path="")

def _parse_csv_env(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]

CORS_ORIGINS = _parse_csv_env(os.environ.get("CORS_ALLOW_ORIGINS", "*")) or ["*"]
TARGET_ALLOWLIST = _parse_csv_env(os.environ.get("GATEWAY_TARGET_ALLOWLIST", ""))

def _normalize_timeout_seconds(timeout_ms) -> float:
    try:
        timeout = float(timeout_ms) / 1000.0
    except (TypeError, ValueError):
        timeout = 10.0
    return max(0.1, min(timeout, 60.0))

def _is_allowed_target(target_url: str) -> tuple[bool, str]:
    parsed = urlparse(target_url)
    if parsed.scheme not in ("http", "https"):
        return False, "targetUrl must use http:// or https://"

    if TARGET_ALLOWLIST and not any(target_url.startswith(prefix) for prefix in TARGET_ALLOWLIST):
        return False, "targetUrl is not in GATEWAY_TARGET_ALLOWLIST"

    return True, ""

@app.after_request
def _add_cors_headers(response):
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
    return ("", 204)

@app.route("/api/proxy-send", methods=["POST"])
def proxy_send():
    body = request.get_json(silent=True) or {}
    target_url = body.get("targetUrl")
    payload = body.get("payload") or {}
    timeout_seconds = _normalize_timeout_seconds(body.get("timeoutMs", 10000))

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
        raw_text = error.read().decode("utf-8", errors="replace")
        status = error.code
        status_text = error.reason or ""
    except URLError as error:
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

    try:
        parsed_json = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed_json = None

    return jsonify(
        {
            "ok": 200 <= status < 300,
            "status": status,
            "statusText": status_text,
            "text": raw_text,
            "json": parsed_json,
        }
    ), 200

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
    response = send_from_directory(PUBLIC_DIR, "index.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route("/<path:asset_path>", methods=["GET"])
def serve_static(asset_path: str):
    candidate = (PUBLIC_DIR / asset_path).resolve()
    if candidate.exists() and candidate.is_file():
        return send_from_directory(PUBLIC_DIR, asset_path)
    response = send_from_directory(PUBLIC_DIR, "index.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8090"))
    app.run(host=host, port=port)
