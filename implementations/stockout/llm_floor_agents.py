"""
Shared Convener → Planner → Procurement → Carrier (OpenAI + Floor request/release).

Used by `pages/3_LLM_war_room.py` (state prefix `llmwr_`) and `app.py` home (prefix `home_llm_`).
Prompts and model use session keys `llmwr_ta_*` and `llmwr_model` so both pages stay aligned.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import httpx
import streamlit as st

try:
    from streamlit.runtime.state.session_state_proxy import get_session_state
except ImportError:  # very old Streamlit
    get_session_state = None  # type: ignore[misc, assignment]

from floor_helpers import effective_openai_api_key, format_floor_tick_error

REPO_ROOT = Path(__file__).resolve().parent
LLM_AGENTS_DIR = REPO_ROOT / "assets" / "llm_agents"

FLOOR_API = os.environ.get("FLOOR_API", "http://localhost:8787/api/v1").rstrip("/")
CONVERSATION_ID = os.environ.get("FLOOR_DEMO_CONVERSATION_ID", "conference_floor_demo_001")
FLOOR_MANAGER_URI = "tag:floor.manager,2025:manager"

DEFAULT_MODEL = "gpt-4o-mini"
LLM_STEP_DELAY_SEC = 0.0

PLANNER = {
    "name": "Planner (AI)",
    "speakerUri": "tag:demo.floor,2025:planner",
    "priority": 9,
    "emoji": "📊",
}
PROCUREMENT = {
    "name": "Procurement (AI)",
    "speakerUri": "tag:demo.floor,2025:procurement",
    "priority": 8,
    "emoji": "📦",
}
CARRIER = {
    "name": "Carrier (AI)",
    "speakerUri": "tag:demo.floor,2025:carrier",
    "priority": 7,
    "emoji": "🚚",
}
CONVENER = {
    "name": "Convener",
    "speakerUri": "tag:demo.floor,2025:convener",
    "priority": 10,
    "emoji": "🎩",
}

LLM_AGENT_STEPS: tuple[tuple[dict[str, Any], str], ...] = (
    (CONVENER, "convene_invite"),
    (PLANNER, "atp_proposal"),
    (PROCUREMENT, "po_proposal"),
    (CARRIER, "carrier_constraint"),
)

_OPS_AGENT_NAMES: frozenset[str] = frozenset(
    {PLANNER["name"], PROCUREMENT["name"], CARRIER["name"]},
)

_DEMO_AGENT_SPEAKER_URIS: frozenset[str] = frozenset(
    {PLANNER["speakerUri"], PROCUREMENT["speakerUri"], CARRIER["speakerUri"]}
)

# Convener may hold the floor during the opening turn; include in stale-holder cleanup.
_DEMO_FLOOR_SPEAKER_URIS: frozenset[str] = frozenset(
    _DEMO_AGENT_SPEAKER_URIS | {CONVENER["speakerUri"]}
)

LLM_TURN_COUNT = 3

LLM_HITL_APPROVAL_PLANNER_MSG = (
    "**Human approved** the joint LLM proposals. On behalf of Planner, Procurement, and Carrier: "
    "we confirm alignment and will proceed with execution planning as discussed."
)
LLM_HITL_REJECT_USER_MSG = (
    "I **reject** this joint LLM proposal set. Agents must take the floor again with **revised** offers."
)
LLM_HITL_REJECT_CONVENER_MSG = (
    "Acknowledged. **Automatically restarting** the full sequence — Convener opening, then "
    "Planner → Procurement → Carrier — with a fresh model pass. "
    "If you left feedback above, every turn will see it and must address it."
)


def format_hitl_reject_user_transcript(extra_feedback: str | None) -> str:
    """Transcript line for HITL reject; optional human notes for the next LLM round."""
    base = LLM_HITL_REJECT_USER_MSG
    extra = (extra_feedback or "").strip()
    if not extra:
        return base
    return f"{base}\n\n**Human feedback (what should improve):**\n{extra}"


def _read_prompt_file(name: str, fallback: str) -> str:
    p = LLM_AGENTS_DIR / name
    try:
        return p.read_text(encoding="utf-8").strip()
    except OSError:
        return fallback


def _prompt_value_blankish(cur: Any) -> bool:
    """True if the widget/session value should be treated as unset (refill from disk when file has body)."""
    if cur is None:
        return True
    if isinstance(cur, str):
        return not cur.strip()
    return True


def _hydrate_llm_prompt_from_disk(session_key: str, file_name: str, fallback: str) -> None:
    """Ensure `session_key` holds markdown from disk.

    Plain ``st.session_state[key] = disk`` can lose to widget-backed state on the first
    client frame; ``reset_state_value`` matches how Streamlit corrects other widgets.
    """
    disk = _read_prompt_file(file_name, fallback)
    missing = session_key not in st.session_state
    cur = st.session_state.get(session_key)
    blankish = _prompt_value_blankish(cur)
    if missing:
        if get_session_state is not None:
            get_session_state().reset_state_value(session_key, disk)
        else:
            st.session_state[session_key] = disk
        return
    if blankish and bool(disk.strip()):
        if get_session_state is not None:
            get_session_state().reset_state_value(session_key, disk)
        else:
            st.session_state[session_key] = disk


def ensure_shared_llm_prompt_session() -> None:
    """Load `assets/llm_agents/*.md` into `llmwr_ta_*` (shared with home + LLM page)."""
    _hydrate_llm_prompt_from_disk(
        "llmwr_ta_skills",
        "SKILLS.md",
        "# Shared skills\nEdit assets/llm_agents/SKILLS.md on disk.",
    )
    _hydrate_llm_prompt_from_disk("llmwr_ta_planner", "planner.md", "You are Planner (AI).")
    _hydrate_llm_prompt_from_disk(
        "llmwr_ta_procurement",
        "procurement.md",
        "You are Procurement (AI).",
    )
    _hydrate_llm_prompt_from_disk("llmwr_ta_carrier", "carrier.md", "You are Carrier (AI).")
    _hydrate_llm_prompt_from_disk(
        "llmwr_ta_convener",
        "convener.md",
        "You are the Convener for this stockout war room.",
    )
    if "llmwr_model" not in st.session_state:
        st.session_state.llmwr_model = DEFAULT_MODEL


def _k(prefix: str, name: str) -> str:
    return f"{prefix}{name}"


def _fetch_holder(trace_append: Callable[[str, str, int], None]) -> tuple[dict[str, Any] | None, str | None]:
    path = f"/floor/holder/{CONVERSATION_ID}"
    try:
        r = httpx.get(f"{FLOOR_API}{path}", timeout=5.0)
        trace_append("GET", path, r.status_code)
        r.raise_for_status()
        return r.json(), None
    except Exception as exc:
        return None, str(exc)


def _ensure_demo_convener_assigned(trace_append: Callable[[str, str, int], None]) -> None:
    """POST /floor/convener once per session if missing (enables convenerNotice on LLM-only flows)."""
    if st.session_state.get("stockout_demo_convener_assigned_once"):
        return
    st.session_state["stockout_demo_convener_assigned_once"] = True
    try:
        hd, err = _fetch_holder(trace_append)
        if err or not hd:
            return
        if hd.get("convener") is not None and str(hd.get("convener")).strip():
            return
        r = httpx.post(
            f"{FLOOR_API}/floor/convener",
            json={
                "conversation_id": CONVERSATION_ID,
                "convener_speakerUri": CONVENER["speakerUri"],
            },
            timeout=8.0,
        )
        trace_append("POST", "/floor/convener (ensure for governance notices)", r.status_code)
    except Exception:
        pass


def post_convener_notice(
    trace_append: Callable[[str, str, int], None],
    *,
    reason: str,
    message: str,
    target_speaker_uri: str | None = None,
) -> None:
    """POST /floor/convener-notice — real governance text in Floor ``decisions`` (best-effort)."""
    path = "/floor/convener-notice"
    try:
        r = httpx.post(
            f"{FLOOR_API}{path}",
            json={
                "conversation_id": CONVERSATION_ID,
                "convener_speakerUri": CONVENER["speakerUri"],
                "target_speakerUri": target_speaker_uri,
                "reason": reason,
                "message": message,
            },
            timeout=15.0,
        )
        trace_append("POST", path, r.status_code)
    except Exception:
        trace_append("POST", f"{path} (exc)", 0)


def _post_floor_release(
    speaker_uri: str,
    trace_note: str,
    trace_append: Callable[[str, str, int], None],
) -> httpx.Response:
    path_rel = "/floor/release"
    rel = httpx.post(
        f"{FLOOR_API}{path_rel}",
        json={"conversation_id": CONVERSATION_ID, "speakerUri": speaker_uri},
        timeout=15.0,
    )
    trace_append("POST", f"{path_rel}{trace_note}", rel.status_code)
    return rel


def _force_release_floor(
    speaker_uri: str,
    trace_append: Callable[[str, str, int], None],
) -> None:
    try:
        _post_floor_release(speaker_uri, " (cleanup)", trace_append)
    except Exception:
        pass


def _try_revoke_floor_holder(
    target_uri: str,
    trace_append: Callable[[str, str, int], None],
) -> bool:
    target_uri = (target_uri or "").strip()
    if not target_uri:
        return False
    hd, err = _fetch_holder(trace_append)
    if err or not hd:
        return False
    conv = hd.get("convener")
    actor = conv or FLOOR_MANAGER_URI
    try:
        r = httpx.post(
            f"{FLOOR_API}/floor/revoke",
            json={
                "conversation_id": CONVERSATION_ID,
                "convener_speakerUri": actor,
                "target_speakerUri": target_uri,
                "reason": "@war-room-llm-auto-recover",
            },
            timeout=15.0,
        )
        trace_append("POST", "/floor/revoke", r.status_code)
        return r.status_code == 200
    except Exception:
        return False


def transcript_tail_operational_indices(
    msgs: list[dict[str, Any]], *, max_count: int = LLM_TURN_COUNT
) -> list[int]:
    """Indices of the latest consecutive Planner/Procurement/Carrier assistant rows (max ``max_count``)."""
    out: list[int] = []
    n = len(msgs)
    for i in range(n - 1, -1, -1):
        m = msgs[i]
        if m.get("role") == "assistant" and m.get("name") in _OPS_AGENT_NAMES:
            out.append(i)
            if len(out) >= max_count:
                break
        elif out:
            break
    return list(reversed(out))


def transcript_operational_hitl_ready(msgs: list[dict[str, Any]]) -> bool:
    return len(transcript_tail_operational_indices(msgs)) >= LLM_TURN_COUNT


def revoke_operational_agents_floor(trace_append: Callable[[str, str, int], None]) -> None:
    """Best-effort revoke for demo Planner / Procurement / Carrier (convener- or manager-mediated)."""
    for uri in (PLANNER["speakerUri"], PROCUREMENT["speakerUri"], CARRIER["speakerUri"]):
        _try_revoke_floor_holder(uri, trace_append)


def _clear_stale_demo_holders(trace_append: Callable[[str, str, int], None]) -> None:
    for _ in range(8):
        hd, err = _fetch_holder(trace_append)
        if err or not hd:
            return
        h = (hd.get("holder") or "").strip()
        if not h:
            return
        if h not in _DEMO_FLOOR_SPEAKER_URIS:
            return
        try:
            rel = _post_floor_release(h, " (pre-request)", trace_append)
            if rel.status_code >= 400:
                _try_revoke_floor_holder(h, trace_append)
        except Exception:
            _try_revoke_floor_holder(h, trace_append)
        time.sleep(0.1)


def _openai_chat(
    *, system: str, user: str, model: str, api_key: str
) -> tuple[str, dict[str, Any]]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "Install the OpenAI SDK: `pip install openai` (see requirements.txt)."
        ) from exc

    client = OpenAI(api_key=api_key)
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.55,
        max_tokens=700,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    choice = resp.choices[0].message
    text = (choice.content or "").strip()
    if not text:
        raise RuntimeError("Empty model response")
    usage = getattr(resp, "usage", None)
    meta: dict[str, Any] = {
        "resolved_model": getattr(resp, "model", None) or model,
        "completion_id": getattr(resp, "id", None),
        "latency_ms": latency_ms,
        "prompt_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
        "completion_tokens": getattr(usage, "completion_tokens", None) if usage else None,
    }
    return text, meta


def _build_user_message(
    *,
    skills_catalog: str,
    agent_label: str,
    prior_snippets: list[str],
    human_round_feedback: str | None = None,
) -> str:
    joined = "\n\n---\n\n".join(prior_snippets) if prior_snippets else "(no prior agent messages yet)"
    fb = (human_round_feedback or "").strip()
    human_fb_block = ""
    if fb:
        human_fb_block = (
            "## Human feedback (previous round rejected)\n"
            "The human operator **rejected** the last joint proposals and asks for a **revised** line. "
            "Respond concretely to every point below in your new offer.\n\n"
            f"{fb}\n\n"
        )
    return (
        f"## Shared skills / context\n{skills_catalog}\n\n"
        "## Crisis scenario\n"
        "SKU **SKU-MOTOR-12** at **DC-EU-01** — assume a stockout war room. "
        "Floor turns are enforced by the host app; you only produce your role’s proposal.\n\n"
        f"{human_fb_block}"
        "## Prior agent outputs\n"
        f"{joined}\n\n"
        f"## Your turn\n"
        f"You are **{agent_label}**. Reply with your proposal only (no preface about being an AI)."
    )


def _build_convener_user_message(
    *, skills_catalog: str, human_round_feedback: str | None = None
) -> str:
    fb = (human_round_feedback or "").strip()
    rerun_block = ""
    if fb:
        rerun_block = (
            "## Human feedback (re-run after rejection)\n"
            "The human **rejected** the previous round. Acknowledge that briefly, then steer the session so the "
            "three operational agents directly address the concerns below in their **new** proposals.\n\n"
            f"{fb}\n\n"
        )
    return (
        f"## Shared skills / context\n{skills_catalog}\n\n"
        "## Crisis scenario\n"
        "SKU **SKU-MOTOR-12** at **DC-EU-01** — critical stockout; EU line at risk.\n\n"
        f"{rerun_block}"
        "## Floor run order (fixed by the host)\n"
        "After your message the host will run, in order: **Planner (AI)** → **Procurement (AI)** → **Carrier (AI)** "
        "(Floor priorities 9 → 8 → 7). Operational agents have not spoken yet.\n\n"
        "## Your turn\n"
        "You are the **Convener**. Deliver your opening: convene the room, invite the three roles in that priority "
        "order, and note that you will revoke stale floor holds if needed after human approval."
    )


def _append_internal_transcript(
    state_prefix: str,
    role: str,
    name: str,
    content: str,
    emoji: str,
) -> None:
    row = {
        "role": role,
        "name": name,
        "content": content,
        "emoji": emoji,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    st.session_state[_k(state_prefix, "transcript")].append(row)


def enqueue_llm_floor_sequence(
    state_prefix: str,
    trace_append: Callable[[str, str, int], None],
    *,
    human_round_feedback: str | None = None,
) -> None:
    """Start Convener → Planner → Procurement → Carrier (LLM); clears HITL gate for this prefix."""
    ensure_shared_llm_prompt_session()
    _ensure_demo_convener_assigned(trace_append)
    st.session_state[_k(state_prefix, "hitl_awaiting")] = False
    st.session_state[_k(state_prefix, "error")] = None
    _clear_stale_demo_holders(trace_append)
    prompts = {
        CONVENER["speakerUri"]: st.session_state.llmwr_ta_convener,
        PLANNER["speakerUri"]: st.session_state.llmwr_ta_planner,
        PROCUREMENT["speakerUri"]: st.session_state.llmwr_ta_procurement,
        CARRIER["speakerUri"]: st.session_state.llmwr_ta_carrier,
    }
    fb = (human_round_feedback or "").strip()
    st.session_state[_k(state_prefix, "script")] = {
        "i": 0,
        "agents": list(LLM_AGENT_STEPS),
        "prompts": prompts,
        "skills_catalog": st.session_state.llmwr_ta_skills,
        "prior_outputs": [],
        "model": st.session_state.get("llmwr_model", DEFAULT_MODEL),
        "api_key": effective_openai_api_key(),
        "human_round_feedback": fb if fb else None,
    }


def tick_llm_floor_sequence(
    state_prefix: str,
    *,
    trace_append: Callable[[str, str, int], None],
    trace_max: int,
    home_transcript_append: Callable[[str, str, str, str], None] | None,
    home_spotlight_append: Callable[[str, str, str, str], None] | None,
    done_toast_key: str | None,
    done_toast_message: str,
) -> None:
    """
    Run at most one LLM agent step for `state_prefix`.

    When `home_transcript_append` is set (home page), assistant lines go there instead of
    `{prefix}transcript`; otherwise messages append to `{prefix}transcript` (LLM page).
    """
    pending_key = _k(state_prefix, "script")
    pending = st.session_state.get(pending_key)
    if not pending:
        return

    transcript_key = _k(state_prefix, "transcript")
    if transcript_key not in st.session_state:
        st.session_state[transcript_key] = []

    agents: list[tuple[dict[str, Any], str]] = pending["agents"]
    i = int(pending["i"])
    if i >= len(agents):
        st.session_state[pending_key] = None
        return
    if i > 0 and LLM_STEP_DELAY_SEC > 0:
        time.sleep(LLM_STEP_DELAY_SEC)

    agent, reason = agents[i]
    api_key = (pending.get("api_key") or "").strip()
    model = pending.get("model") or DEFAULT_MODEL
    if not api_key:
        st.session_state[pending_key] = None
        st.session_state[_k(state_prefix, "error")] = "OpenAI API key missing."
        return

    system_prompt = pending["prompts"].get(agent["speakerUri"], "")
    skills_catalog = pending.get("skills_catalog", "")
    prior = pending.get("prior_outputs", [])
    human_fb = pending.get("human_round_feedback")

    def _append_assistant(name: str, content: str, emoji: str) -> None:
        if home_transcript_append is not None:
            home_transcript_append("assistant", name, content, emoji)
            if home_spotlight_append is not None:
                home_spotlight_append("assistant", name, content, emoji)
        else:
            _append_internal_transcript(state_prefix, "assistant", name, content, emoji)

    try:
        _clear_stale_demo_holders(trace_append)

        path_req = "/floor/request"
        req_payload = {
            "conversation_id": CONVERSATION_ID,
            "speakerUri": agent["speakerUri"],
            "priority": agent["priority"],
            "reason": reason,
        }

        if agent["speakerUri"] != CONVENER["speakerUri"]:
            post_convener_notice(
                trace_append,
                reason=f"invite_{reason}",
                target_speaker_uri=agent["speakerUri"],
                message=(
                    f"Convener invites **{agent['name']}** to request the floor next "
                    f"(floor request reason `{reason}`, priority {agent['priority']}). "
                    "Proceed with your proposal when granted."
                ),
            )

        def _floor_request(trace_suffix: str = "") -> tuple[httpx.Response, dict[str, Any]]:
            r = httpx.post(
                f"{FLOOR_API}{path_req}",
                json=req_payload,
                timeout=30.0,
            )
            trace_append("POST", f"{path_req}{trace_suffix}", r.status_code)
            r.raise_for_status()
            return r, r.json()

        _, data = _floor_request()
        if not data.get("granted"):
            hd0, _ = _fetch_holder(trace_append)
            stuck = (hd0 or {}).get("holder")
            if isinstance(stuck, str) and stuck.strip():
                _try_revoke_floor_holder(stuck.strip(), trace_append)
            _clear_stale_demo_holders(trace_append)
            time.sleep(0.15)
            _, data = _floor_request(" (retry)")

        if not data.get("granted"):
            st.session_state[pending_key] = None
            hd, _ = _fetch_holder(trace_append)
            cur = (hd or {}).get("holder")
            cur_s = f" Current holder: `{cur}`." if cur else ""
            detail = ""
            try:
                detail = " " + json.dumps(data, ensure_ascii=False)[:400]
            except (TypeError, ValueError):
                detail = " " + str(data)[:400]
            st.session_state[_k(state_prefix, "error")] = (
                f"Floor still busy after auto release/revoke/retry — {agent['name']} did not get the turn.{cur_s}{detail} "
                "Try revokeFloor on the home page for this conversation, or another speaker may hold the floor."
            )
            return

        hold_acquired = True
        try:
            if agent["speakerUri"] == CONVENER["speakerUri"]:
                user_msg = _build_convener_user_message(
                    skills_catalog=skills_catalog, human_round_feedback=human_fb
                )
            else:
                user_msg = _build_user_message(
                    skills_catalog=skills_catalog,
                    agent_label=agent["name"],
                    prior_snippets=prior,
                    human_round_feedback=human_fb,
                )
            reply, oa_meta = _openai_chat(
                system=system_prompt, user=user_msg, model=model, api_key=api_key
            )
            trace_append(
                "POST",
                f"[openai] chat.completions ({oa_meta.get('resolved_model', model)})",
                200,
            )
            st.session_state[_k(state_prefix, "last_openai")] = {
                "agent": agent["name"],
                "requested_model": model,
                "time_utc": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                **oa_meta,
                "reply_preview": (reply[:400] + "…") if len(reply) > 400 else reply,
            }
            prior.append(f"**{agent['name']}:**\n{reply}")
            pending["prior_outputs"] = prior

            _append_assistant(agent["name"], reply, agent["emoji"])
            if agent["speakerUri"] == CONVENER["speakerUri"]:
                post_convener_notice(
                    trace_append,
                    reason="convene_opening_llm",
                    message=reply,
                )

            path_rel = "/floor/release"
            rel = httpx.post(
                f"{FLOOR_API}{path_rel}",
                json={
                    "conversation_id": CONVERSATION_ID,
                    "speakerUri": agent["speakerUri"],
                },
                timeout=30.0,
            )
            trace_append("POST", path_rel, rel.status_code)
            rel.raise_for_status()
            hold_acquired = False

            pending["i"] = i + 1
            if pending["i"] >= len(agents):
                st.session_state[pending_key] = None
                st.session_state[_k(state_prefix, "hitl_awaiting")] = True
                # Fresh widget keys each HITL round (Streamlit can reuse stale button state otherwise).
                seq_key = f"{state_prefix}hitl_seq"
                st.session_state[seq_key] = int(st.session_state.get(seq_key, 0)) + 1
                if done_toast_key:
                    st.session_state[done_toast_key] = done_toast_message
        finally:
            if hold_acquired:
                _force_release_floor(agent["speakerUri"], trace_append)
    except Exception as exc:
        st.session_state[pending_key] = None
        st.session_state[_k(state_prefix, "error")] = format_floor_tick_error(exc, floor_api=FLOOR_API)

    # trim trace if this prefix keeps a trace buffer (LLM page)
    tk = _k(state_prefix, "trace")
    if tk in st.session_state and isinstance(st.session_state[tk], list):
        st.session_state[tk] = st.session_state[tk][-trace_max:]


def init_llm_page_session() -> None:
    """Streamlit session defaults for the LLM multipage app."""
    if _k("llmwr_", "transcript") not in st.session_state:
        st.session_state[_k("llmwr_", "transcript")] = []
    if _k("llmwr_", "hitl_awaiting") not in st.session_state:
        st.session_state[_k("llmwr_", "hitl_awaiting")] = False
    if _k("llmwr_", "tw_epoch") not in st.session_state:
        st.session_state[_k("llmwr_", "tw_epoch")] = 0
    if _k("llmwr_", "trace") not in st.session_state:
        st.session_state[_k("llmwr_", "trace")] = []
    ensure_shared_llm_prompt_session()
