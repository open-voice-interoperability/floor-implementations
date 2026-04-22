"""Shared helpers for `app.py`, multipage scripts, and the Floor decisions log."""

from __future__ import annotations

import html
import os
from typing import Any

import httpx
import streamlit as st

FLOOR_API = os.environ.get("FLOOR_API", "http://localhost:8787/api/v1").rstrip("/")
CONVERSATION_ID = os.environ.get("FLOOR_DEMO_CONVERSATION_ID", "conference_floor_demo_001")


def floor_api_root_url(api_base: str | None = None) -> str:
    """Strip ``/api/v1`` for health checks (e.g. ``http://host:8787``)."""
    api = (api_base or FLOOR_API).rstrip("/")
    return api.removesuffix("/api/v1") if api.endswith("/api/v1") else api


def is_floor_connection_error(message: str | None) -> bool:
    """True for typical \"nothing listening\" / DNS failures from httpx."""
    if not message:
        return False
    m = message.lower()
    return (
        "connection refused" in m
        or "errno 61" in m
        or "errno 111" in m
        or "actively refused" in m
        or "name or service not known" in m
        or "nodename nor servname" in m
    )


def format_floor_tick_error(exc: BaseException, *, floor_api: str | None = None) -> str:
    """Short message for ``st.error`` when agent turns cannot reach the Floor API."""
    api = (floor_api or FLOOR_API).rstrip("/")
    root = floor_api_root_url(api)
    raw = str(exc)
    if isinstance(exc, httpx.ConnectError) or is_floor_connection_error(raw):
        return (
            "Floor API unreachable (connection refused). In the STOCKOUT folder run `docker compose up -d`, "
            f"then `curl {root}/health`, and refresh. Target: `{api}`"
        )
    return raw


def war_room_floor_offline_markdown(floor_api: str | None = None) -> str:
    """Banner copy when GET holder fails because the Floor process is down."""
    api = (floor_api or FLOOR_API).rstrip("/")
    root = floor_api_root_url(api)
    return (
        f"**Floor API offline** — nothing accepted a connection at `{api}`.\n\n"
        f"- From **this STOCKOUT folder**: `docker compose up -d` (bundled Floor + stock mock), then check "
        f"`curl -s {root}/health`.\n"
        f"- Stock mock: `curl -s http://localhost:8890/health` (same compose).\n\n"
        "**Refresh** this page after the API is listening."
    )


# Streamlit session key for the OpenAI API key widget (shared: `app.py` + `pages/3_LLM_war_room.py`).
WAR_ROOM_OPENAI_KEY_SES = "war_room_openai_api_key"


def _openai_key_from_environment() -> str:
    """Return `OPENAI_API_KEY` from the process environment (strip whitespace)."""
    return (os.environ.get("OPENAI_API_KEY") or "").strip()


def ensure_war_room_openai_session_key() -> None:
    """Initialize `st.session_state[WAR_ROOM_OPENAI_KEY_SES]` from env when missing or empty."""
    env_k = _openai_key_from_environment()
    if WAR_ROOM_OPENAI_KEY_SES not in st.session_state:
        init = env_k
        if not init:
            init = (st.session_state.get("llmwr_openai_key") or "").strip()
        st.session_state[WAR_ROOM_OPENAI_KEY_SES] = init
        return
    cur = (st.session_state.get(WAR_ROOM_OPENAI_KEY_SES) or "").strip()
    if env_k and not cur:
        st.session_state[WAR_ROOM_OPENAI_KEY_SES] = env_k


def effective_openai_api_key() -> str:
    """Key for OpenAI calls: sidebar/session value, else `OPENAI_API_KEY` from the environment."""
    cur = (st.session_state.get(WAR_ROOM_OPENAI_KEY_SES) or "").strip()
    if cur:
        return cur
    return _openai_key_from_environment()


def environment_openai_key_present() -> bool:
    return bool(_openai_key_from_environment())


def fetch_floor_holder_silent() -> tuple[dict[str, Any] | None, str | None]:
    """GET holder + decisions without side effects (for log page)."""
    path = f"/floor/holder/{CONVERSATION_ID}"
    try:
        resp = httpx.get(f"{FLOOR_API}{path}", timeout=5.0)
        resp.raise_for_status()
        return resp.json(), None
    except Exception as exc:
        return None, str(exc)


def render_decisions_log_section(
    data: dict[str, Any] | None,
    fetch_error: str | None,
) -> None:
    """Governance events log only (compact style)."""
    st.markdown("**Decisions log (latest)**")
    if fetch_error:
        st.error(f"Floor API unreachable: {fetch_error}")
        st.caption(f"Check `docker compose up` in the FLOOR repo and `FLOOR_API` (current: `{FLOOR_API}`).")
        return

    assert data is not None
    decisions = data.get("decisions") or []
    if not decisions:
        st.info("No governance events yet.")
        return

    log_lines: list[str] = []
    for d in decisions[-80:]:
        ts = d.get("timestamp", "")
        ev = d.get("eventType", "")
        sp = d.get("speakerUri", "")
        rs = d.get("reason")
        det = d.get("detail")
        tail = ""
        if rs:
            tail += f"  │  {rs}"
        if det:
            tail += f"  │  {det}"
        log_lines.append(f"{ts}  │  {ev}  │  {sp}{tail}")

    log_html = (
        '<div style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:0.78rem;'
        "line-height:1.45;background:#0f172a;color:#e2e8f0;padding:14px 16px;border-radius:10px;"
        'border:1px solid #334155;max-height:70vh;overflow-y:auto;text-align:left;">'
    )
    for raw in log_lines:
        esc = html.escape(raw)
        log_html += f'<div style="border-bottom:1px solid #1e293b;padding:6px 0;">{esc}</div>'
    log_html += "</div>"
    st.markdown(log_html, unsafe_allow_html=True)

    st.caption(
        "Includes **convenerNotice** rows when the war room posts convener directives via "
        "`POST …/floor/convener-notice`. Updates on each page rerun. "
        f"SSE for external clients: `{FLOOR_API}/events/floor/{CONVERSATION_ID}`"
    )
