"""Dedicated page: Floor governance events log only (not on home)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from floor_helpers import CONVERSATION_ID, FLOOR_API, fetch_floor_holder_silent, render_decisions_log_section

# Absolute path to multipage entrypoint (st.page_link("app.py") can fail from pages/).
_WAR_ROOM_ENTRY = Path(__file__).resolve().parent.parent / "app.py"

st.set_page_config(
    page_title="Floor decisions log",
    page_icon="📋",
    layout="wide",
)

st.title("📋 Floor decisions log")
st.caption(
    f"Conversation `{CONVERSATION_ID}` · `{FLOOR_API}` — "
    "open this page when you need a full governance audit."
)

c1, c2 = st.columns((1, 4))
with c1:
    if st.button("← War room", help="Back to war room home"):
        st.switch_page(_WAR_ROOM_ENTRY)
with c2:
    if st.button("Refresh log"):
        st.rerun()

data, err = fetch_floor_holder_silent()
render_decisions_log_section(data, err)
