#!/usr/bin/env python3
"""
War room — stockout crisis + OFP floor (Streamlit).

Home: **LLM** agent turns spotlight at the top (with post-run **HITL** approve/reject); full transcript; API trace and summary; governance log in `pages/…`.

Run (from this folder):
  streamlit run app.py

Requires: Floor API (e.g. FLOOR repo `docker compose up`, :8787).
Optional: stock mock on STOCK_API (default :8890).
"""

from __future__ import annotations

import html
import importlib.util
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import streamlit as st

from floor_helpers import (
    WAR_ROOM_OPENAI_KEY_SES,
    ensure_war_room_openai_session_key,
    effective_openai_api_key,
    is_floor_connection_error,
    war_room_floor_offline_markdown,
)
from war_room_ui import inject_war_room_compact_css, scroll_main_to_agent_focus

from llm_floor_agents import (
    CARRIER,
    CONVENER,
    LLM_HITL_APPROVAL_PLANNER_MSG,
    LLM_HITL_REJECT_CONVENER_MSG,
    LLM_TURN_COUNT,
    PLANNER,
    PROCUREMENT,
    enqueue_llm_floor_sequence,
    ensure_shared_llm_prompt_session,
    format_hitl_reject_user_transcript,
    revoke_operational_agents_floor,
    tick_llm_floor_sequence,
    post_convener_notice,
    transcript_tail_operational_indices,
)
from llm_typewriter_ui import render_typewriter_iframe, typewriter_storage_key

from stockout_mcp.client import (
    parse_inventory_json,
    run_mcp_get_inventory_sync,
    stock_mcp_runtime_available,
)

REPO_ROOT = Path(__file__).resolve().parent
SKILL_PATH = REPO_ROOT / "assets" / "SKILL.md"
SPEC_LOOKUP_PATH = REPO_ROOT / "assets" / "spec_lookup.py"

FLOOR_API = os.environ.get("FLOOR_API", "http://localhost:8787/api/v1").rstrip("/")
STOCK_API = os.environ.get("STOCK_API", "http://localhost:8890").rstrip("/")
CONVERSATION_ID = os.environ.get("FLOOR_DEMO_CONVERSATION_ID", "conference_floor_demo_001")
FLOOR_MANAGER_URI = "tag:floor.manager,2025:manager"

HUMAN_NAME = os.environ.get("FLOOR_DEMO_HUMAN_NAME", "Diego")
HUMAN_SPEAKER_URI = os.environ.get(
    "FLOOR_DEMO_HUMAN_SPEAKER_URI",
    "tag:demo.floor,2025:diego",
)
HUMAN_EMOJI = "👤"

# Demo crisis (same defaults as sidebar stock check).
_CRISIS_SKU = "SKU-MOTOR-12"
_CRISIS_LOC = "DC-EU-01"

API_TRACE_MAX = 40
HOME_LLM_PREFIX = "home_llm_"
# Minimum pause before chained reruns while an LLM sequence runs (typewriter needs time to paint).
HOME_LLM_TYPEWRITER_RERUN_PAUSE_SEC = 0.9
HOME_LLM_TYPEWRITER_RERUN_PAUSE_CAP_SEC = 12.0


def _streamlit_page_href(slug: str) -> str:
    """Browser path for a multipage slug (honours `server.baseUrlPath` when set)."""
    try:
        from streamlit import config as _st_config

        base = (_st_config.get_option("server.baseUrlPath") or "").strip("/")
    except Exception:
        base = ""
    slug = slug.strip("/")
    if base:
        return f"/{base}/{slug}"
    return f"/{slug}"


def _enqueue_home_llm_floor_sequence(*, human_round_feedback: str | None = None) -> None:
    """Start home LLM run (single source of truth: transcript_messages)."""
    enqueue_llm_floor_sequence(
        HOME_LLM_PREFIX,
        _api_trace_append,
        human_round_feedback=human_round_feedback,
    )


def _tail_llm_agent_indices(msgs: list[dict[str, Any]]) -> list[int]:
    """Indices of the latest consecutive Planner/Procurement/Carrier rows at the end of msgs (max 3)."""
    return transcript_tail_operational_indices(msgs)


def _spotlight_rows_from_transcript(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [msgs[i] for i in _tail_llm_agent_indices(msgs)]


def _home_spotlight_hitl_ready(msgs: list[dict[str, Any]]) -> bool:
    return len(_tail_llm_agent_indices(msgs)) >= LLM_TURN_COUNT


def _home_llm_typewriter_rerun_pause_sec() -> float:
    """Longer replies need a longer gap before the next Streamlit rerun remounts iframes."""
    if not st.session_state.get("home_llm_typewriter", True):
        return 0.0
    msgs: list[dict[str, Any]] = st.session_state.transcript_messages
    if not msgs:
        return HOME_LLM_TYPEWRITER_RERUN_PAUSE_SEC
    last = msgs[-1]
    if last.get("name") not in _HOME_TYPEWRITER_NAMES:
        return HOME_LLM_TYPEWRITER_RERUN_PAUSE_SEC
    n = len(str(last.get("content") or ""))
    ms_per_char = 14.0 / 1000.0
    return min(
        HOME_LLM_TYPEWRITER_RERUN_PAUSE_CAP_SEC,
        max(HOME_LLM_TYPEWRITER_RERUN_PAUSE_SEC, n * ms_per_char * 1.08),
    )

PLANNER = {
    "name": "Planner (AI)",
    "speakerUri": "tag:demo.floor,2025:planner",
    "priority": 9,
    "emoji": "📊",
    "opening": (
        "ATP proposal: transfer 200 units from DC-US-01 to DC-EU-01; "
        "estimated ETA +48h if we confirm inter-hub booking today."
    ),
}
PROCUREMENT = {
    "name": "Procurement (AI)",
    "speakerUri": "tag:demo.floor,2025:procurement",
    "priority": 8,
    "emoji": "📦",
    "opening": (
        "Procurement proposal: expedite PO on batch 7 (supplier X); +72h lead time "
        "but unlocks partial production while waiting on the transfer."
    ),
}
CARRIER = {
    "name": "Carrier (AI)",
    "speakerUri": "tag:demo.floor,2025:carrier",
    "priority": 7,
    "emoji": "🚚",
    "opening": (
        "Carrier constraint: pickup at DC-US-01 by Friday 14:00 UTC; "
        "after that window the slot moves to Monday (higher cost)."
    ),
}

# Typewriter on the home transcript for these assistant names (spotlight HITL still uses operational tail only).
_HOME_TYPEWRITER_NAMES = frozenset(
    {PLANNER["name"], PROCUREMENT["name"], CARRIER["name"], CONVENER["name"]},
)
_OPS_LLM_TRANSCRIPT_NAMES = frozenset(
    {PLANNER["name"], PROCUREMENT["name"], CARRIER["name"]},
)

_SCROLL_ABOVE_AGENT_HINT = "Scroll above for agent conversation updates"

st.set_page_config(
    page_title="War room — stockout & floor",
    page_icon="🚨",
    layout="wide",
)


def _load_spec_lookup() -> Any:
    spec = importlib.util.spec_from_file_location(
        "stockout_spec_lookup",
        SPEC_LOOKUP_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load spec_lookup module")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _append_transcript(role: str, name: str, content: str, emoji: str) -> None:
    st.session_state.transcript_messages.append(
        {
            "role": role,
            "name": name,
            "content": content,
            "emoji": emoji,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }
    )


def _render_chat_message_body(
    *,
    msg_idx: int,
    total_messages: int,
    msg: dict[str, Any],
    tw_epoch: int,
    typewriter_on: bool,
    storage_namespace: str,
    only_llm_floor_agents: bool,
) -> None:
    """Typewriter only on the last line so one agent animates at a time (sequential, not parallel)."""
    is_last = msg_idx == total_messages - 1
    is_asst = msg.get("role") == "assistant"
    if not (typewriter_on and is_asst and is_last and msg.get("content")):
        st.markdown(msg["content"])
        return
    if only_llm_floor_agents and msg.get("name") not in _HOME_TYPEWRITER_NAMES:
        st.markdown(msg["content"])
        return
    sk = typewriter_storage_key(
        tw_epoch,
        msg_idx,
        str(msg.get("timestamp", "")),
        str(msg["content"]),
        namespace=storage_namespace,
    )
    render_typewriter_iframe(str(msg["content"]), storage_key=sk)


def _api_trace_append(method: str, path: str, status_code: int) -> None:
    """Append a short Floor/stock API line to session trace."""
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"{ts}  {method:4}  {path}  →  {status_code}"
    st.session_state.api_trace.append(line)
    st.session_state.api_trace = st.session_state.api_trace[-API_TRACE_MAX:]


def _render_stockout_crisis_banner() -> None:
    """Persistent crisis strip at the top of the war room (English UI)."""
    mcp_extra = ""
    if st.session_state.get("war_room_mcp_startup_stockout"):
        mcp_extra = (
            '<div style="font-size:0.82rem;color:#7f1d1d;margin-top:8px;line-height:1.4;">'
            "Session MCP check: <strong>stockout confirmed</strong> for the crisis SKU at this location."
            "</div>"
        )
    st.markdown(
        f"""
        <div style="border:1px solid #fecaca;background:linear-gradient(95deg,#fff1f2 0%,#ffffff 58%);
        border-radius:10px;padding:12px 14px 12px 16px;margin:0 0 10px 0;
        display:flex;gap:14px;align-items:flex-start;box-shadow:0 1px 2px rgba(0,0,0,0.05);">
          <div aria-hidden="true" style="font-size:1.85rem;line-height:1;">🚨</div>
          <div>
            <div style="font-weight:700;font-size:1.08rem;letter-spacing:-0.02em;color:#9f1239;">
              Stockout — critical situation
            </div>
            <div style="font-size:0.88rem;color:#444;margin-top:6px;line-height:1.45;">
              Active crisis: <strong>{_CRISIS_SKU}</strong> @ <strong>{_CRISIS_LOC}</strong> — EU line at risk.
              The <strong>Convener</strong> is registered on the Floor automatically; use <strong>Run agents</strong>
              to open the session (Convener invites Planner → Procurement → Carrier by priority).
            </div>
            {mcp_extra}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _fetch_floor_holder() -> tuple[dict[str, Any] | None, str | None]:
    """GET holder + decisions; records trace on success."""
    path = f"/floor/holder/{CONVERSATION_ID}"
    try:
        resp = httpx.get(f"{FLOOR_API}{path}", timeout=5.0)
        _api_trace_append("GET", path, resp.status_code)
        resp.raise_for_status()
        return resp.json(), None
    except Exception as exc:
        return None, str(exc)


def _ensure_war_room_auto_convener() -> None:
    """POST /floor/convener once per session when holder has no convener (demo path)."""
    if st.session_state.get("war_room_auto_convener_tried"):
        return
    st.session_state.war_room_auto_convener_tried = True
    try:
        holder, err = _fetch_floor_holder()
        if err or not holder:
            return
        cur = holder.get("convener")
        if cur is not None and str(cur).strip():
            return
        r = httpx.post(
            f"{FLOOR_API}/floor/convener",
            json={
                "conversation_id": CONVERSATION_ID,
                "convener_speakerUri": CONVENER["speakerUri"],
            },
            timeout=8.0,
        )
        _api_trace_append("POST", "/floor/convener (auto-assign)", r.status_code)
    except Exception:
        pass


def _maybe_startup_mcp_critical_stock() -> None:
    """Once per session: optional MCP inventory for crisis SKU; transcript + banner if stockout."""
    if st.session_state.get("war_room_mcp_startup_done"):
        return
    st.session_state.war_room_mcp_startup_done = True
    if not stock_mcp_runtime_available():
        return
    try:
        ok, body, ms = run_mcp_get_inventory_sync(STOCK_API, _CRISIS_SKU, _CRISIS_LOC)
        trace_status = 200 if ok else 502
        _api_trace_append(
            "MCP",
            f"startup tool get_inventory(sku={_CRISIS_SKU}, loc={_CRISIS_LOC}) {ms}ms",
            trace_status,
        )
        if not ok:
            return
        data = parse_inventory_json(body)
        if not isinstance(data, dict):
            return
        stockout = bool(data.get("stockout"))
        st.session_state.war_room_mcp_startup_stockout = stockout
        if stockout:
            _mcp_convener_body = (
                "**Critical stockout** — MCP inventory on session open confirms `stockout` for "
                f"`{_CRISIS_SKU}` @ `{_CRISIS_LOC}`. I am on the Floor as convener; when you run **Run agents**, "
                "I will invite Planner, then Procurement, then Carrier, in that priority order."
            )
            _append_transcript(
                "assistant",
                CONVENER["name"],
                _mcp_convener_body,
                CONVENER["emoji"],
            )
            post_convener_notice(
                _api_trace_append,
                reason="mcp_session_stockout",
                message=_mcp_convener_body,
            )
            # Remount typewriter iframe so the convener line animates like other floor agents.
            st.session_state.home_llm_tw_epoch = int(st.session_state.get("home_llm_tw_epoch", 0)) + 1
    except Exception:
        pass


def _render_floor_trace_panel(fetch_error: str | None) -> None:
    """API call trace only; full governance log is on a separate page."""
    st.subheader("Floor — API trace")
    st.caption(
        "Floor, stock, **MCP** (stock tool), and **OpenAI** calls from **Agent turns (LLM)** appear here "
        "(including **`POST [openai] chat.completions (...)`** after each model step). "
        "Governance event log: **Floor decisions log** (sidebar)."
    )
    if fetch_error:
        if is_floor_connection_error(fetch_error):
            st.warning(war_room_floor_offline_markdown(FLOOR_API))
        else:
            st.warning(
                f"GET holder failed: {fetch_error} — holder summary on the right may be stale."
            )

    trace_lines = list(st.session_state.api_trace)
    trace_body = (
        "\n".join(reversed(trace_lines[-35:]))
        if trace_lines
        else "(no calls traced in this session yet)"
    )
    st.markdown("### Recent call trace")
    st.caption("Newest lines at the **top**. Same column as this panel — scroll down from **Transcript** until you see this bordered box.")
    with st.container(border=True):
        st.code(trace_body, language=None)

    st.page_link(
        "pages/2_Floor_decisions_log.py",
        label="Open Floor decisions log (dedicated page)",
        icon="📋",
    )


def _render_agent_turns_spotlight() -> None:
    """Top-of-page spotlight: last LLM trio from transcript only (no duplicate storage)."""
    script_key = f"{HOME_LLM_PREFIX}script"
    hitl_key = f"{HOME_LLM_PREFIX}hitl_awaiting"
    active = bool(st.session_state.get(script_key))
    hitl = bool(st.session_state.get(hitl_key))
    if not active and not hitl:
        return

    msgs: list[dict[str, Any]] = st.session_state.transcript_messages
    rows = _spotlight_rows_from_transcript(msgs)
    if not rows and not active:
        return

    _hitl_seq = int(st.session_state.get(f"{HOME_LLM_PREFIX}hitl_seq", 0))

    with st.container(key="war_room_spotlight_sticky"):
        with st.container(border=True):
            st.markdown("#### Convener → Planner → Procurement → Carrier (LLM)")
            if active:
                st.caption(
                    "**One speaker at a time** on the Floor: Convener opens, then the three operational agents "
                    "in priority order (no artificial delay between turns). "
                    "**This panel stays pinned** while you scroll the transcript."
                )
            elif hitl and rows:
                st.caption(
                    "**Human in the loop** — after the three operational proposals below, choose **Approve** or **Reject**."
                )
            _tw_epoch = int(st.session_state.get("home_llm_tw_epoch", 0))
            _tw_on = bool(st.session_state.get("home_llm_typewriter", True))
            _nrows = len(rows)
            for idx, msg in enumerate(rows):
                with st.chat_message(msg["role"], avatar=msg.get("emoji", "💬")):
                    st.markdown(f"**{msg['name']}** · `{msg.get('timestamp', '')}`")
                    _render_chat_message_body(
                        msg_idx=idx,
                        total_messages=_nrows,
                        msg=msg,
                        tw_epoch=_tw_epoch,
                        typewriter_on=_tw_on,
                        storage_namespace="home",
                        only_llm_floor_agents=False,
                    )
            if active and len(rows) == 0:
                st.caption("Connecting to Floor and OpenAI for the first turn…")
            # Convener turn is not in the operational tail: mirror the latest Convener line here so it stays in view.
            if active and msgs:
                _last = msgs[-1]
                if (
                    _last.get("role") == "assistant"
                    and _last.get("name") == CONVENER["name"]
                    and _last.get("content")
                ):
                    st.caption("**Current turn** (same message is in the full transcript below)")
                    with st.chat_message("assistant", avatar=CONVENER["emoji"]):
                        st.markdown(f"**{_last['name']}** · `{_last.get('timestamp', '')}`")
                        _render_chat_message_body(
                            msg_idx=0,
                            total_messages=1,
                            msg=_last,
                            tw_epoch=_tw_epoch,
                            typewriter_on=_tw_on,
                            storage_namespace="home",
                            only_llm_floor_agents=True,
                        )

            if hitl and not active and _home_spotlight_hitl_ready(msgs):
                st.divider()
                with st.container(border=True):
                    st.markdown("##### Your decision")
                    st.caption(
                        "**Approve** adds a Planner confirmation and ends this round. "
                        "**Reject** logs your veto and immediately starts another **LLM** round (fresh model pass). "
                        "Optional feedback is passed to **every** agent turn in the new round (including Convener)."
                    )
                    _fb_key = f"{HOME_LLM_PREFIX}reject_feedback_{_hitl_seq}"
                    st.text_area(
                        "Optional feedback if you reject (what to fix or rethink)",
                        placeholder="Leave empty to reject without extra guidance.",
                        key=_fb_key,
                        height=80,
                    )
                    a1, a2 = st.columns(2)
                    with a1:
                        if st.button(
                            "Approve joint LLM proposals",
                            type="primary",
                            key=f"hitl_approve_{_hitl_seq}",
                            use_container_width=True,
                            help="Lock the plan; append Planner confirmation to the transcript.",
                        ):
                            st.session_state[hitl_key] = False
                            _append_transcript(
                                "assistant",
                                PLANNER["name"],
                                LLM_HITL_APPROVAL_PLANNER_MSG,
                                PLANNER["emoji"],
                            )
                            revoke_operational_agents_floor(_api_trace_append)
                            _hitl_close = (
                                "**Round closed** — I revoked any residual Floor holds for Planner, Procurement, "
                                "and Carrier where the API still showed them as targets (demo governance cleanup)."
                            )
                            _append_transcript(
                                "assistant",
                                CONVENER["name"],
                                _hitl_close,
                                CONVENER["emoji"],
                            )
                            post_convener_notice(
                                _api_trace_append,
                                reason="hitl_approve_round_closed",
                                message=_hitl_close,
                            )
                            st.rerun()
                    with a2:
                        if st.button(
                            "Reject — run LLM round again",
                            key=f"hitl_reject_{_hitl_seq}",
                            use_container_width=True,
                            help="Record rejection and re-run Planner → Procurement → Carrier with OpenAI.",
                        ):
                            st.session_state[hitl_key] = False
                            _fb_raw = str(st.session_state.get(_fb_key, "") or "").strip()
                            _append_transcript(
                                "user",
                                HUMAN_NAME,
                                format_hitl_reject_user_transcript(_fb_raw or None),
                                HUMAN_EMOJI,
                            )
                            _append_transcript(
                                "assistant",
                                CONVENER["name"],
                                LLM_HITL_REJECT_CONVENER_MSG,
                                CONVENER["emoji"],
                            )
                            _enqueue_home_llm_floor_sequence(
                                human_round_feedback=_fb_raw or None,
                            )
                            st.rerun()


def _render_floor_right_summary(data: dict[str, Any] | None, fetch_error: str | None) -> None:
    """Compact holder and convener."""
    st.subheader("Floor summary")
    if fetch_error:
        st.caption("Holder data unavailable (see warning in the trace panel).")
        return
    assert data is not None
    holder = data.get("holder")
    conv = data.get("convener")
    st.markdown(f"**Holder**  \n`{holder or '—'}`")
    st.markdown(f"**Convener**  \n`{conv if conv is not None else '—'}`")


def _home_llm_script_tick() -> None:
    """Run at most one OpenAI + Floor step for the home-page agent spotlight."""
    tick_llm_floor_sequence(
        HOME_LLM_PREFIX,
        trace_append=_api_trace_append,
        trace_max=API_TRACE_MAX,
        home_transcript_append=_append_transcript,
        home_spotlight_append=None,
        done_toast_key="agent_script_message",
        done_toast_message=(
            "LLM agent sequence completed — use **Approve** or **Reject** in the spotlight above."
        ),
    )


if "transcript_messages" not in st.session_state:
    st.session_state.transcript_messages = []
if "api_trace" not in st.session_state:
    st.session_state.api_trace = []
if "home_llm_tw_epoch" not in st.session_state:
    st.session_state.home_llm_tw_epoch = 0
ensure_war_room_openai_session_key()
ensure_shared_llm_prompt_session()

_ensure_war_room_auto_convener()
_maybe_startup_mcp_critical_stock()

_home_llm_script_tick()

floor_data, floor_err = _fetch_floor_holder()

st.title("🚨 War room — stockout & floor (OFP demo)")
st.caption(
    f"You are **{HUMAN_NAME}** (logistics / control tower). "
    "Agent turns are **highlighted at the top**; below: full transcript, API trace, and floor summary. "
    "Governance log: **Floor decisions log** in the sidebar. "
    f"`{CONVERSATION_ID}` · Floor API `{FLOOR_API}` · Stock API `{STOCK_API}`"
)
if floor_err and is_floor_connection_error(floor_err):
    st.warning(war_room_floor_offline_markdown(FLOOR_API))
inject_war_room_compact_css()
if toast := st.session_state.pop("agent_script_message", None):
    st.success(toast)
if err_toast := st.session_state.pop(f"{HOME_LLM_PREFIX}error", None):
    st.error(err_toast)

_render_stockout_crisis_banner()
if st.session_state.get("war_room_mcp_last_body"):
    with st.expander("Last MCP stock query (this session)", expanded=False):
        _mok = st.session_state.get("war_room_mcp_last_ok")
        _mms = int(st.session_state.get("war_room_mcp_last_ms") or 0)
        st.caption(f"MCP tool **get_inventory** · success={_mok} · {_mms} ms")
        st.code(st.session_state.get("war_room_mcp_last_body", ""), language="json")
_render_agent_turns_spotlight()
_script_ui = bool(st.session_state.get(f"{HOME_LLM_PREFIX}script"))
_hitl_ui = bool(st.session_state.get(f"{HOME_LLM_PREFIX}hitl_awaiting"))
if _script_ui or _hitl_ui:
    scroll_main_to_agent_focus()

with st.sidebar:
    st.subheader("Agent turns")
    st.markdown(
        """
        <style>
        div[data-testid="stSidebar"] .st-key-home_llm_run_btn button {
            background-color: #2563eb !important;
            color: #ffffff !important;
            border: 1px solid #1d4ed8 !important;
        }
        div[data-testid="stSidebar"] .st-key-home_llm_run_btn button:hover {
            background-color: #1d4ed8 !important;
            border-color: #1e3a8a !important;
        }
        div[data-testid="stSidebar"] .st-key-home_llm_run_btn button:disabled {
            background-color: #93c5fd !important;
            color: #e0e7ff !important;
            border-color: #93c5fd !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    _sk = f"{HOME_LLM_PREFIX}script"
    _hk = f"{HOME_LLM_PREFIX}hitl_awaiting"
    _llm_busy = bool(st.session_state.get(_sk)) or bool(st.session_state.get(_hk))
    if st.button(
        "Run agents",
        disabled=_llm_busy,
        type="primary",
        key="home_llm_run_btn",
        use_container_width=True,
        help=(
            "OpenAI + Floor: Convener opening, then Planner → Procurement → Carrier (same as **LLM agents** page). "
            "Then approve or reject in the spotlight."
        ),
    ):
        _enqueue_home_llm_floor_sequence()
        st.rerun()
    if st.session_state.get(_sk):
        st.caption("Running — one agent per refresh.")
    elif st.session_state.get(_hk):
        st.caption("**HITL:** approve or reject in the spotlight above.")
    st.checkbox(
        "Typewriter (assistant replies)",
        value=True,
        key="home_llm_typewriter",
        help=(
            "Character-by-character only for the **latest** agent line (one animation at a time). "
            "Pauses between automatic steps so typing can finish before the next agent. "
            "Completed lines show in full; localStorage keeps them instant on refresh."
        ),
    )

    st.divider()
    st.header("Configuration")
    st.page_link(
        "pages/2_Floor_decisions_log.py",
        label="Floor decisions log",
        icon="📋",
        help="Governance event audit (GET holder), outside the home page.",
    )
    _llm_href = _streamlit_page_href("LLM_war_room")
    st.markdown(
        "<style>"
        "a.llm-war-room-hard-link{display:inline-flex;align-items:center;gap:0.35rem;padding:0.15rem 0;"
        "font-size:0.875rem;font-weight:500;text-decoration:none;color:inherit;}"
        "a.llm-war-room-hard-link:hover{text-decoration:underline;}"
        "</style>"
        f'<a class="llm-war-room-hard-link" href="{html.escape(_llm_href)}" target="_self">'
        "🤖 LLM agents (OpenAI)</a>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Same-tab **full reload** (not Streamlit soft nav) so the LLM page always boots cleanly."
    )
    st.caption(f"Human: **{HUMAN_NAME}** · `{HUMAN_SPEAKER_URI}`")
    ensure_war_room_openai_session_key()
    st.text_input(
        "OpenAI API Key (optional)",
        type="password",
        key=WAR_ROOM_OPENAI_KEY_SES,
        help=(
            "Used for **Agent turns** on this page and on **LLM agents (OpenAI)**. "
            "If unset here, **OPENAI_API_KEY** from the environment is used."
        ),
    )
    _k = effective_openai_api_key()
    if _k:
        os.environ["OPENAI_API_KEY"] = _k
    st.selectbox(
        "OpenAI model",
        options=["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"],
        index=0,
        key="llmwr_model",
        help="Same session field as **LLM agents (OpenAI)** — one model choice for both pages.",
    )

    st.divider()
    st.subheader("Inventory (stock mock)")
    sku_stock = st.text_input("SKU", value="SKU-MOTOR-12")
    loc_stock = st.text_input("Location", value="DC-EU-01")
    if st.button("Check stock (HTTP)"):
        try:
            url = f"{STOCK_API}/inventory/{sku_stock}"
            r = httpx.get(url, params={"location_id": loc_stock}, timeout=5.0)
            _api_trace_append("GET", f"[stock] /inventory/{sku_stock}", r.status_code)
            if r.status_code == 404:
                st.warning("SKU/location not found (is the stock API up?)")
            else:
                r.raise_for_status()
                data = r.json()
                pretty = json.dumps(data, indent=2, ensure_ascii=False)
                stockout = data.get("stockout", False)
                alert = (
                    f"**Inventory alert** — `{sku_stock}` @ `{loc_stock}`\n\n"
                    f"```json\n{pretty}\n```\n\n"
                    + (
                        "⚠️ **Stockout** — war room convening; convener is auto-assigned on the home page when unset."
                        if stockout
                        else "Situation under control (no stockout)."
                    )
                )
                _append_transcript("user", HUMAN_NAME, alert, HUMAN_EMOJI)
                st.success("Inventory response added to transcript")
                st.rerun()
        except Exception as exc:
            st.error(f"Stock API unreachable ({STOCK_API}): {exc}")

    st.divider()
    st.subheader("Stock via MCP (lite)")
    st.caption(
        "Explicit **Model Context Protocol** round-trip: Streamlit spawns a stdio MCP server "
        f"that calls **{STOCK_API}** (same HTTP contract as above). "
        "Check the **API trace** for `MCP` lines after you click."
    )
    if not stock_mcp_runtime_available():
        st.info(
            "MCP Python SDK not installed in this venv — HTTP stock check above still works. "
            "For the MCP demo: `pip install -r requirements-mcp-demo.txt` then restart Streamlit."
        )
    elif st.button(
        "Query stock via MCP (`get_inventory`)",
        key="war_room_mcp_stock_btn",
        help="Spawns stockout_mcp.server over stdio; tool performs GET /inventory/{sku}.",
    ):
        ok, body, ms = run_mcp_get_inventory_sync(STOCK_API, sku_stock, loc_stock)
        st.session_state.war_room_mcp_last_ok = ok
        st.session_state.war_room_mcp_last_body = body
        st.session_state.war_room_mcp_last_ms = ms
        trace_status = 200 if ok else 502
        _api_trace_append(
            "MCP",
            f"tool get_inventory(sku={sku_stock}, loc={loc_stock}) {ms}ms",
            trace_status,
        )
        if ok:
            data = parse_inventory_json(body)
            if isinstance(data, dict):
                pretty = json.dumps(data, indent=2, ensure_ascii=False)
                stockout = bool(data.get("stockout"))
                alert = (
                    f"**Inventory (via MCP)** — `{sku_stock}` @ `{loc_stock}`\n\n"
                    f"```json\n{pretty}\n```\n\n"
                    + (
                        "⚠️ **Stockout** — war room convening; convener is auto-assigned on the home page when unset."
                        if stockout
                        else "Situation under control (no stockout)."
                    )
                )
                _append_transcript("user", HUMAN_NAME, alert, HUMAN_EMOJI)
                st.success("MCP tool completed — response added to transcript.")
            else:
                st.warning("MCP returned non-JSON text; see expander on main page.")
        else:
            st.error(f"MCP call failed: {body[:500]}")
        st.rerun()

    st.divider()
    st.subheader("Convener (OFP 1.1.0)")
    st.caption(
        "On **home** load, the UI assigns the demo convener once if the Floor has none. "
        "Use the buttons below only to override or clear."
    )
    default_convener = CONVENER["speakerUri"]
    convener_uri = st.text_input(
        "Convener speakerUri",
        value=default_convener,
        help="Must match the convener tag (e.g. …:convener, not …:convene).",
    )
    if st.button("Assign convener"):
        try:
            r = httpx.post(
                f"{FLOOR_API}/floor/convener",
                json={
                    "conversation_id": CONVERSATION_ID,
                    "convener_speakerUri": convener_uri,
                },
                timeout=5.0,
            )
            _api_trace_append("POST", "/floor/convener", r.status_code)
            if r.status_code == 200:
                st.success("Convener assigned")
            else:
                st.error(r.text)
        except Exception as exc:
            st.error(str(exc))

    if st.button("Clear convener"):
        try:
            r = httpx.post(
                f"{FLOOR_API}/floor/convener",
                json={"conversation_id": CONVERSATION_ID, "convener_speakerUri": None},
                timeout=5.0,
            )
            _api_trace_append("POST", "/floor/convener", r.status_code)
            st.success("Convener cleared") if r.status_code == 200 else st.error(r.text)
        except Exception as exc:
            st.error(str(exc))

    st.divider()
    st.subheader("Skill + spec")
    if st.button("Apply checklist (Skill file)"):
        try:
            text = SKILL_PATH.read_text(encoding="utf-8")
            snippet = "\n".join(text.splitlines()[:12])
            _append_transcript(
                "assistant",
                "SkillChecklist",
                "From SKILL.md (excerpt):\n\n" + snippet,
                "📜",
            )
            st.success("Skill added to transcript")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    if st.button("Lookup OFP spec (HTTP)"):
        try:
            mod = _load_spec_lookup()
            title = mod.fetch_spec_heading_sync(3.0)
            _append_transcript(
                "assistant",
                "SpecWitness",
                "Spec title (lookup):\n\n" + title,
                "🌐",
            )
            st.success("Spec added to transcript")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    st.divider()
    st.subheader("revokeFloor demo")
    target = st.text_input("Target speakerUri", value=PLANNER["speakerUri"])
    rev_reason = st.text_input("Reason", value="@override")
    if st.button("Revoke floor"):
        try:
            hpath = f"/floor/holder/{CONVERSATION_ID}"
            hr = httpx.get(f"{FLOOR_API}{hpath}", timeout=5.0)
            _api_trace_append("GET", hpath, hr.status_code)
            holder = hr.json()
            conv = holder.get("convener")
            actor = conv or FLOOR_MANAGER_URI
            r = httpx.post(
                f"{FLOOR_API}/floor/revoke",
                json={
                    "conversation_id": CONVERSATION_ID,
                    "convener_speakerUri": actor,
                    "target_speakerUri": target,
                    "reason": rev_reason,
                },
                timeout=5.0,
            )
            _api_trace_append("POST", "/floor/revoke", r.status_code)
            if r.status_code == 200:
                st.success("Revoke applied")
            else:
                st.error(r.text)
        except Exception as exc:
            st.error(str(exc))


st.subheader("Transcript (war room)")
_msgs = st.session_state.transcript_messages
_script_open = bool(st.session_state.get(f"{HOME_LLM_PREFIX}script"))
_hitl_open = bool(st.session_state.get(f"{HOME_LLM_PREFIX}hitl_awaiting"))
_spotlight_dup_idx = (
    frozenset(_tail_llm_agent_indices(_msgs)) if (_script_open or _hitl_open) else frozenset()
)
_visible_msgs = [(i, m) for i, m in enumerate(_msgs) if i not in _spotlight_dup_idx]
_tw_epoch = int(st.session_state.get("home_llm_tw_epoch", 0))
_tw_on = bool(st.session_state.get("home_llm_typewriter", True))
_nvis = len(_visible_msgs)
for vis_idx, (orig_idx, msg) in enumerate(_visible_msgs):
    with st.chat_message(msg["role"], avatar=msg.get("emoji", "💬")):
        st.markdown(f"**{msg['name']}** · `{msg.get('timestamp','')}`")
        _render_chat_message_body(
            msg_idx=vis_idx,
            total_messages=_nvis,
            msg=msg,
            tw_epoch=_tw_epoch,
            typewriter_on=_tw_on,
            storage_namespace="home",
            only_llm_floor_agents=True,
        )
    if (
        (_script_open or _hitl_open)
        and msg.get("role") == "assistant"
        and msg.get("name") == CONVENER["name"]
        and any(
            _msgs[j].get("name") in _OPS_LLM_TRANSCRIPT_NAMES
            for j in range(orig_idx + 1, len(_msgs))
        )
    ):
        st.caption(_SCROLL_ABOVE_AGENT_HINT)

if not st.session_state.transcript_messages:
    st.info(
        "The transcript fills from **sidebar** actions: inventory, agent turns, "
        "skill, spec lookup (and revoke if you try it)."
    )
elif _spotlight_dup_idx and (_script_open or _hitl_open):
    st.caption(
        "The latest Planner / Procurement / Carrier lines are shown **above** in the spotlight "
        "(hidden here to avoid duplicates)."
    )

st.divider()
trace_col, summary_col = st.columns((1.65, 1.0))
with trace_col:
    _render_floor_trace_panel(floor_err)
with summary_col:
    _render_floor_right_summary(floor_data, floor_err)

st.divider()
c1, c2, c3 = st.columns(3)
with c1:
    if st.button("Clear transcript"):
        st.session_state.transcript_messages = []
        st.session_state.pop(f"{HOME_LLM_PREFIX}script", None)
        st.session_state[f"{HOME_LLM_PREFIX}hitl_awaiting"] = False
        st.session_state.home_llm_tw_epoch = int(st.session_state.get("home_llm_tw_epoch", 0)) + 1
        st.rerun()
with c2:
    if st.button("Refresh page"):
        st.rerun()
with c3:
    st.caption("Server-side floor state: restart the API or change `FLOOR_DEMO_CONVERSATION_ID`.")

if st.session_state.get(f"{HOME_LLM_PREFIX}script"):
    _pause = _home_llm_typewriter_rerun_pause_sec()
    if _pause > 0:
        time.sleep(_pause)
    st.rerun()
