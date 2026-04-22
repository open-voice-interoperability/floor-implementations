"""
OpenAI-powered Planner → Procurement → Carrier (same Floor request/release as the home page).

Prompts default from `assets/llm_agents/*.md`; editable in-session via the sidebar expander.
"""

from __future__ import annotations

import html
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import streamlit as st
import streamlit.components.v1 as components

from war_room_ui import inject_war_room_compact_css, scroll_main_to_agent_focus

from floor_helpers import (
    WAR_ROOM_OPENAI_KEY_SES,
    ensure_war_room_openai_session_key,
    environment_openai_key_present,
)

from llm_typewriter_ui import render_typewriter_iframe, typewriter_storage_key

from llm_floor_agents import (
    CARRIER,
    CONVERSATION_ID,
    FLOOR_API,
    CONVENER,
    LLM_HITL_APPROVAL_PLANNER_MSG,
    LLM_HITL_REJECT_CONVENER_MSG,
    LLM_TURN_COUNT,
    format_hitl_reject_user_transcript,
    PLANNER,
    PROCUREMENT,
    _read_prompt_file,
    enqueue_llm_floor_sequence,
    ensure_shared_llm_prompt_session,
    init_llm_page_session,
    post_convener_notice,
    revoke_operational_agents_floor,
    tick_llm_floor_sequence,
    transcript_tail_operational_indices,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
LLM_AGENTS_DIR = REPO_ROOT / "assets" / "llm_agents"
STOCK_API = os.environ.get("STOCK_API", "http://localhost:8890").rstrip("/")

HUMAN_NAME = os.environ.get("FLOOR_DEMO_HUMAN_NAME", "Diego")
HUMAN_EMOJI = "👤"

LLM_TRACE_MAX = 40
LLM_TYPEWRITER_RERUN_PAUSE_SEC = 0.9
LLM_TYPEWRITER_RERUN_PAUSE_CAP_SEC = 12.0

_LLM_TW_AGENT_NAMES = frozenset(
    {PLANNER["name"], PROCUREMENT["name"], CARRIER["name"]},
)
_LLM_PAGE_TYPEWRITER_NAMES = frozenset(_LLM_TW_AGENT_NAMES | {CONVENER["name"]})
_OPS_LLM_TRANSCRIPT_NAMES = frozenset(
    {PLANNER["name"], PROCUREMENT["name"], CARRIER["name"]},
)
_SCROLL_ABOVE_AGENT_HINT = "Scroll above for agent conversation updates"


def _tail_llm_agent_indices_llm(msgs: list[dict[str, Any]]) -> list[int]:
    return transcript_tail_operational_indices(msgs)


def _spotlight_rows_from_transcript_llm(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [msgs[i] for i in _tail_llm_agent_indices_llm(msgs)]


def _llm_page_spotlight_hitl_ready(msgs: list[dict[str, Any]]) -> bool:
    return len(_tail_llm_agent_indices_llm(msgs)) >= LLM_TURN_COUNT


def _render_chat_message_body_llm(
    *,
    msg_idx: int,
    total_messages: int,
    msg: dict[str, Any],
    tw_epoch: int,
    typewriter_on: bool,
    only_llm_floor_agents: bool,
) -> None:
    is_last = msg_idx == total_messages - 1
    is_asst = msg.get("role") == "assistant"
    if not (typewriter_on and is_asst and is_last and msg.get("content")):
        st.markdown(msg["content"])
        return
    if only_llm_floor_agents and msg.get("name") not in _LLM_PAGE_TYPEWRITER_NAMES:
        st.markdown(msg["content"])
        return
    sk = typewriter_storage_key(
        tw_epoch,
        msg_idx,
        str(msg.get("timestamp", "")),
        str(msg["content"]),
        namespace="llmwr",
    )
    render_typewriter_iframe(str(msg["content"]), storage_key=sk)


def _render_llm_agent_turns_spotlight() -> None:
    """Pinned panel: operational trio + optional Convener mirror + HITL (same UX as home)."""
    active = bool(st.session_state.get("llmwr_script"))
    hitl = bool(st.session_state.get("llmwr_hitl_awaiting"))
    if not active and not hitl:
        return

    msgs: list[dict[str, Any]] = st.session_state.llmwr_transcript
    rows = _spotlight_rows_from_transcript_llm(msgs)
    if not rows and not active:
        return

    _hitl_seq = int(st.session_state.get("llmwr_hitl_seq", 0))

    with st.container(key="war_room_spotlight_sticky"):
        with st.container(border=True):
            st.markdown("#### Convener → Planner → Procurement → Carrier (LLM)")
            if active:
                st.caption(
                    "**One speaker at a time** on the Floor: Convener opens, then the three operational agents "
                    "in priority order. **This panel stays pinned** while you scroll the transcript."
                )
            elif hitl and rows:
                st.caption(
                    "**Human in the loop** — after the three operational proposals below, choose **Approve** or **Reject**."
                )
            _tw_epoch = int(st.session_state.get("llmwr_tw_epoch", 0))
            _tw_on = bool(st.session_state.get("llmwr_typewriter", True))
            _nrows = len(rows)
            for idx, msg in enumerate(rows):
                with st.chat_message(msg["role"], avatar=msg.get("emoji", "💬")):
                    st.markdown(f"**{msg['name']}** · `{msg.get('timestamp', '')}`")
                    _render_chat_message_body_llm(
                        msg_idx=idx,
                        total_messages=_nrows,
                        msg=msg,
                        tw_epoch=_tw_epoch,
                        typewriter_on=_tw_on,
                        only_llm_floor_agents=False,
                    )
            if active and len(rows) == 0:
                st.caption("Connecting to Floor and OpenAI for the first turn…")
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
                        _render_chat_message_body_llm(
                            msg_idx=0,
                            total_messages=1,
                            msg=_last,
                            tw_epoch=_tw_epoch,
                            typewriter_on=_tw_on,
                            only_llm_floor_agents=True,
                        )

            if hitl and not active and _llm_page_spotlight_hitl_ready(msgs):
                st.divider()
                with st.container(border=True):
                    st.markdown("##### Your decision")
                    st.caption(
                        "**Approve** adds a Planner confirmation and ends this round. "
                        "**Reject** logs your veto and immediately starts another **LLM** round. "
                        "Optional feedback is passed to **every** agent turn in the new round (including Convener)."
                    )
                    _fb_key = f"llmwr_reject_feedback_{_hitl_seq}"
                    st.text_area(
                        "Optional feedback if you reject",
                        placeholder="Leave empty to reject without extra guidance.",
                        key=_fb_key,
                        height=80,
                    )
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button(
                            "Approve joint LLM proposals",
                            type="primary",
                            key=f"llmwr_hitl_approve_{_hitl_seq}",
                            use_container_width=True,
                        ):
                            st.session_state.llmwr_hitl_awaiting = False
                            _append_msg(
                                "assistant",
                                PLANNER["name"],
                                LLM_HITL_APPROVAL_PLANNER_MSG,
                                PLANNER["emoji"],
                            )
                            revoke_operational_agents_floor(_trace_append)
                            _hitl_close = (
                                "**Round closed** — I revoked any residual Floor holds for Planner, Procurement, "
                                "and Carrier where the API still showed them as targets (demo governance cleanup)."
                            )
                            _append_msg(
                                "assistant",
                                CONVENER["name"],
                                _hitl_close,
                                CONVENER["emoji"],
                            )
                            post_convener_notice(
                                _trace_append,
                                reason="hitl_approve_round_closed",
                                message=_hitl_close,
                            )
                            st.rerun()
                    with c2:
                        if st.button(
                            "Reject — run LLM round again",
                            key=f"llmwr_hitl_reject_{_hitl_seq}",
                            use_container_width=True,
                        ):
                            st.session_state.llmwr_hitl_awaiting = False
                            _fb_raw = str(st.session_state.get(_fb_key, "") or "").strip()
                            _append_msg(
                                "user",
                                HUMAN_NAME,
                                format_hitl_reject_user_transcript(_fb_raw or None),
                                HUMAN_EMOJI,
                            )
                            _append_msg(
                                "assistant",
                                CONVENER["name"],
                                LLM_HITL_REJECT_CONVENER_MSG,
                                CONVENER["emoji"],
                            )
                            _enqueue_llm_script_from_session(human_round_feedback=_fb_raw or None)
                            st.rerun()


def _llm_war_room_reload_href() -> str:
    """Same-tab URL for a full browser load of this page (sidebar soft-nav workaround)."""
    try:
        from streamlit import config as _st_config

        base = (_st_config.get_option("server.baseUrlPath") or "").strip("/")
    except Exception:
        base = ""
    if base:
        return f"/{base}/LLM_war_room?prompts=1"
    return "/LLM_war_room?prompts=1"


def _llm_typewriter_rerun_pause_sec() -> float:
    if not st.session_state.get("llmwr_typewriter", True):
        return 0.0
    msgs: list[dict[str, Any]] = st.session_state.get("llmwr_transcript") or []
    if not msgs:
        return LLM_TYPEWRITER_RERUN_PAUSE_SEC
    last = msgs[-1]
    if not (
        last.get("role") == "assistant"
        and last.get("name") in _LLM_PAGE_TYPEWRITER_NAMES
        and last.get("content")
    ):
        return LLM_TYPEWRITER_RERUN_PAUSE_SEC
    n = len(str(last.get("content") or ""))
    ms_per_char = 14.0 / 1000.0
    return min(
        LLM_TYPEWRITER_RERUN_PAUSE_CAP_SEC,
        max(LLM_TYPEWRITER_RERUN_PAUSE_SEC, n * ms_per_char * 1.08),
    )


st.set_page_config(
    page_title="LLM agents — war room",
    page_icon="🤖",
    layout="wide",
)

# Eager defaults before any widget binds to `llmwr_ta_*` keys (avoids first-paint empty text areas).
init_llm_page_session()
ensure_war_room_openai_session_key()


def _save_llm_agent_files() -> str:
    """Persist current text areas to assets/llm_agents/*.md"""
    LLM_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    mapping = {
        "SKILLS.md": st.session_state.llmwr_ta_skills,
        "convener.md": st.session_state.llmwr_ta_convener,
        "planner.md": st.session_state.llmwr_ta_planner,
        "procurement.md": st.session_state.llmwr_ta_procurement,
        "carrier.md": st.session_state.llmwr_ta_carrier,
    }
    for fname, body in mapping.items():
        (LLM_AGENTS_DIR / fname).write_text(body, encoding="utf-8")
    return "Saved to `assets/llm_agents/` (SKILLS.md + convener + planner / procurement / carrier)."


def _reload_llm_agent_files_into_session() -> None:
    st.session_state.llmwr_ta_skills = _read_prompt_file(
        "SKILLS.md",
        "# Shared skills\nEdit assets/llm_agents/SKILLS.md on disk.",
    )
    st.session_state.llmwr_ta_convener = _read_prompt_file(
        "convener.md",
        "You are the Convener for this stockout war room.",
    )
    st.session_state.llmwr_ta_planner = _read_prompt_file("planner.md", "You are Planner (AI).")
    st.session_state.llmwr_ta_procurement = _read_prompt_file("procurement.md", "You are Procurement (AI).")
    st.session_state.llmwr_ta_carrier = _read_prompt_file("carrier.md", "You are Carrier (AI).")


def _trace_append(method: str, path: str, status: int) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"{ts}  {method:4}  {path}  →  {status}"
    st.session_state.llmwr_trace.append(line)
    st.session_state.llmwr_trace = st.session_state.llmwr_trace[-LLM_TRACE_MAX:]


def _fetch_holder() -> tuple[dict[str, Any] | None, str | None]:
    path = f"/floor/holder/{CONVERSATION_ID}"
    try:
        r = httpx.get(f"{FLOOR_API}{path}", timeout=5.0)
        _trace_append("GET", path, r.status_code)
        r.raise_for_status()
        return r.json(), None
    except Exception as exc:
        return None, str(exc)


def _append_msg(role: str, name: str, content: str, emoji: str) -> None:
    row = {
        "role": role,
        "name": name,
        "content": content,
        "emoji": emoji,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    st.session_state.llmwr_transcript.append(row)


def _enqueue_llm_script_from_session(*, human_round_feedback: str | None = None) -> None:
    """Start Convener → Planner → Procurement → Carrier (LLM); clears HITL gate."""
    enqueue_llm_floor_sequence(
        "llmwr_",
        _trace_append,
        human_round_feedback=human_round_feedback,
    )


def _llm_script_tick() -> None:
    tick_llm_floor_sequence(
        "llmwr_",
        trace_append=_trace_append,
        trace_max=LLM_TRACE_MAX,
        home_transcript_append=None,
        home_spotlight_append=None,
        done_toast_key="llmwr_done_toast",
        done_toast_message=(
            "LLM agent sequence completed — use **Approve** or **Reject** in the spotlight above."
        ),
    )


_llm_script_tick()

st.title("🤖 LLM war room — Convener + operational agents")
st.caption(
    "OpenAI-backed turns with the **same Floor request/release** as the war room home page: "
    "**Convener** opens, then Planner → Procurement → Carrier. "
    "After those three operational proposals, **Human in the loop** (approve / reject) appears in the **pinned spotlight** "
    "at the top (same as home). "
    "Optional **typewriter** effect for the latest assistant line (sidebar). "
    "Each turn adds **`[openai] chat.completions`** to the trace. "
    f"`{CONVERSATION_ID}` · `{FLOOR_API}` · stock `{STOCK_API}`"
)
st.info(
    "**SKILLS.md** and **convener + planner / procurement / carrier** system prompts live in the block "
    "just below — edit there, then **Save prompts to disk** (or use the same actions in the sidebar)."
)

_, _mid_reload, _ = st.columns([1, 2, 1])
with _mid_reload:
    st.markdown("##### Prompts from disk")
    st.caption(
        "If you opened this page from the **sidebar** and the **SKILLS / Planner–Carrier** boxes are empty, "
        "click the button below: it performs a **full browser reload** (a new Streamlit session) so the files "
        "under `assets/llm_agents/` show up in the text areas."
    )
    if st.button(
        "🔄 Reload page and show SKILLS + prompts",
        key="llmwr_browser_full_reload",
        type="primary",
        use_container_width=True,
    ):
        components.html(
            "<script>window.top.location.reload();</script>",
            height=0,
            width=0,
        )
    _reload_href = html.escape(_llm_war_room_reload_href())
    st.markdown(
        f'<p style="text-align:center;margin-top:0.5rem;font-size:0.85rem;">'
        f'Alternatively: <a href="{_reload_href}" target="_self">use this link</a> '
        f"(same effect).</p>",
        unsafe_allow_html=True,
    )

if toast := st.session_state.pop("llmwr_done_toast", None):
    st.success(toast)
if err := st.session_state.pop("llmwr_error", None):
    st.error(err)

inject_war_room_compact_css()
_render_llm_agent_turns_spotlight()
_script_ui = bool(st.session_state.get("llmwr_script"))
_hitl_ui = bool(st.session_state.get("llmwr_hitl_awaiting"))
if _script_ui or _hitl_ui:
    scroll_main_to_agent_focus()

# Re-sync from disk after tick / toasts so `llmwr_ta_*` are never left as widget-empty placeholders.
ensure_shared_llm_prompt_session()

with st.expander(
    "**SKILLS.md** + Convener + Planner / Procurement / Carrier prompts (`assets/llm_agents/`)",
    expanded=True,
    key="llmwr_prompts_expander",
):
    st.caption(
        "Files on disk: `SKILLS.md`, `convener.md`, `planner.md`, `procurement.md`, `carrier.md`. "
        "Edit below, then **Save prompts to disk** to persist (or **Reload from disk** to discard in-session edits)."
    )
    st.text_area("Shared SKILLS.md context", key="llmwr_ta_skills", height=200)
    t0, t1, t2, t3 = st.tabs(
        ["Convener", "Planner", "Procurement", "Carrier"],
        key="llmwr_agent_prompt_tabs",
    )
    with t0:
        st.text_area("Convener system prompt", key="llmwr_ta_convener", height=220)
    with t1:
        st.text_area("Planner system prompt", key="llmwr_ta_planner", height=220)
    with t2:
        st.text_area("Procurement system prompt", key="llmwr_ta_procurement", height=220)
    with t3:
        st.text_area("Carrier system prompt", key="llmwr_ta_carrier", height=220)
    sv, rl = st.columns(2)
    with sv:
        if st.button("Save prompts to disk", type="primary", key="llmwr_save_md"):
            try:
                msg = _save_llm_agent_files()
                st.success(msg)
            except OSError as exc:
                st.error(f"Could not save: {exc}")
    with rl:
        if st.button("Reload from disk", key="llmwr_reload_md"):
            _reload_llm_agent_files_into_session()
            st.success("Reloaded markdown from disk.")
            st.rerun()

with st.sidebar:
    ensure_war_room_openai_session_key()
    st.subheader("Navigate")
    if st.button(
        "← War room (home)",
        key="llmwr_nav_home",
        help="Returns to `app.py` (same as Streamlit’s app menu).",
        use_container_width=True,
    ):
        st.switch_page("app.py")
    st.caption("If this fails, use the **app menu** (top-left) and pick the main war room page.")
    st.divider()
    st.header("LLM configuration")
    st.text_input(
        "OpenAI API key",
        type="password",
        key=WAR_ROOM_OPENAI_KEY_SES,
        help=(
            "Same session field as **war room (home)**. "
            "If **OPENAI_API_KEY** is set in the environment, it is copied here when this field is empty, "
            "and the Run button still uses the env value as a fallback."
        ),
    )
    if environment_openai_key_present():
        st.caption(
            "**OPENAI_API_KEY** is set in the environment — the LLM run uses it even if this box looks empty "
            "(password masking)."
        )
    st.selectbox(
        "Model",
        options=[
            "gpt-4o-mini",
            "gpt-4o",
            "gpt-4-turbo",
        ],
        index=0,
        key="llmwr_model",
    )
    busy = bool(st.session_state.get("llmwr_script"))
    hitl_waiting = bool(st.session_state.get("llmwr_hitl_awaiting"))
    if st.button(
        "Run Convener → Planner → Procurement → Carrier (LLM)",
        disabled=busy or hitl_waiting,
        help=(
            "Runs Convener opening then Planner → Procurement → Carrier with OpenAI and Floor request/release. "
            "Disabled while **Human in the loop** is waiting — approve or reject under the transcript first."
        ),
    ):
        _enqueue_llm_script_from_session()
        st.rerun()
    if busy:
        st.caption("LLM sequence running — one agent per refresh (no artificial delay).")
    elif hitl_waiting:
        st.caption("Human in the loop: use **Approve** or **Reject** in the spotlight at the top.")

    st.divider()
    if st.button("Clear LLM transcript", key="llmwr_clear_sidebar"):
        st.session_state.llmwr_transcript = []
        st.session_state.llmwr_hitl_awaiting = False
        st.session_state.llmwr_tw_epoch = int(st.session_state.get("llmwr_tw_epoch", 0)) + 1
        st.rerun()
    st.checkbox(
        "Typewriter (assistant replies)",
        value=True,
        key="llmwr_typewriter",
        help=(
            "Character-by-character only on the **latest** agent line (one at a time, in sequence). "
            "Pauses between steps so each agent can finish typing before the next."
        ),
    )

    st.divider()
    st.subheader("Prompts & SKILLS.md")
    st.caption(
        "Text areas are **below the pinned spotlight** (scroll the main page). "
        "Save writes all five files under `assets/llm_agents/`."
    )
    s1, s2 = st.columns(2)
    with s1:
        if st.button("Save to disk", type="primary", key="llmwr_save_md_sidebar"):
            try:
                msg = _save_llm_agent_files()
                st.success(msg)
            except OSError as exc:
                st.error(f"Could not save: {exc}")
    with s2:
        if st.button("Reload from disk", key="llmwr_reload_md_sidebar"):
            _reload_llm_agent_files_into_session()
            st.success("Reloaded from disk.")
            st.rerun()

floor_data, floor_err = _fetch_holder()

st.subheader("Transcript (LLM)")
_msgs = st.session_state.llmwr_transcript
_script_open = bool(st.session_state.get("llmwr_script"))
_hitl_open = bool(st.session_state.get("llmwr_hitl_awaiting"))
_spotlight_dup_idx = (
    frozenset(_tail_llm_agent_indices_llm(_msgs)) if (_script_open or _hitl_open) else frozenset()
)
_visible_msgs = [(i, m) for i, m in enumerate(_msgs) if i not in _spotlight_dup_idx]
_epoch = int(st.session_state.get("llmwr_tw_epoch", 0))
_tw = bool(st.session_state.get("llmwr_typewriter", True))
_nvis = len(_visible_msgs)
for vis_idx, (orig_idx, msg) in enumerate(_visible_msgs):
    with st.chat_message(msg["role"], avatar=msg.get("emoji", "💬")):
        st.markdown(f"**{msg['name']}** · `{msg.get('timestamp', '')}`")
        _render_chat_message_body_llm(
            msg_idx=vis_idx,
            total_messages=_nvis,
            msg=msg,
            tw_epoch=_epoch,
            typewriter_on=_tw,
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

if not st.session_state.llmwr_transcript:
    st.info("Run the **LLM sequence** from the sidebar after setting your OpenAI key.")
elif _spotlight_dup_idx and (_script_open or _hitl_open):
    st.caption(
        "The latest Planner / Procurement / Carrier lines are shown **above** in the spotlight "
        "(hidden here to avoid duplicates)."
    )

st.divider()
left, right = st.columns((1.6, 1.0))
with left:
    st.subheader("Floor — API trace (this page)")
    body = "\n".join(reversed(st.session_state.llmwr_trace[-30:])) or "(no calls yet)"
    st.code(body, language=None)
    with st.expander("OpenAI call verification (how you know it hit the API)", expanded=False):
        st.markdown(
            "- A **`POST [openai] chat.completions (...)`** row appears in the trace above **after each** "
            "Planner / Procurement / Carrier LLM step.\n"
            "- **`completion_id`** comes from OpenAI’s response (not generated locally).\n"
            "- **Token counts** and **latency** are reported when the API returns them.\n"
            "- Compare with your [OpenAI usage dashboard](https://platform.openai.com/usage) (login required)."
        )
        last = st.session_state.get("llmwr_last_openai")
        if not last:
            st.info("Run **Planner → Procurement → Carrier (LLM)** once; metadata appears here after the first agent returns.")
        else:
            st.json(last)
            st.caption("Preview is the start of the model reply shown in the transcript.")
with right:
    st.subheader("Floor summary")
    if floor_err:
        st.caption("Holder unavailable.")
    else:
        assert floor_data is not None
        st.markdown(f"**Holder**  \n`{floor_data.get('holder') or '—'}`")
        st.markdown(f"**Convener**  \n`{floor_data.get('convener') or '—'}`")

if st.session_state.get("llmwr_script"):
    _pause = _llm_typewriter_rerun_pause_sec()
    if _pause > 0:
        time.sleep(_pause)
    st.rerun()
