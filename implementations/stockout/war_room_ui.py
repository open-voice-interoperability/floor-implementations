"""Shared war-room UI: compact CSS + parent-window scroll for the LLM spotlight.

Streamlit ≥1.40 uses ``section[data-testid="stMain"]`` as the scrollport; older builds used
``section.main``. Targeting only ``section.main`` makes the scroll script a no-op on current
Streamlit, so agents “speak” off-screen until the user scrolls manually.
"""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

# Comma-separated legacy + current main selectors (sticky + chat margins).
_WAR_ROOM_MAIN_SELECTORS = (
    'section[data-testid="stMain"], '
    "section.main"
)

WAR_ROOM_COMPACT_CSS = f"""
<style>
{_WAR_ROOM_MAIN_SELECTORS} [data-testid="stChatMessage"] {{
    padding-top: 0.2rem !important;
    padding-bottom: 0.2rem !important;
    scroll-margin-bottom: 1.25rem;
    scroll-margin-top: 5.5rem;
}}
{_WAR_ROOM_MAIN_SELECTORS} [data-testid="stChatMessage"] p {{
    margin-bottom: 0.15rem;
}}
{_WAR_ROOM_MAIN_SELECTORS} div.st-key-war_room_spotlight_sticky {{
    position: sticky;
    top: 3.75rem;
    z-index: 50;
    background: linear-gradient(
        180deg,
        var(--background-color, #ffffff) 0%,
        var(--background-color, #ffffff) 92%,
        rgba(255, 255, 255, 0) 100%
    );
    padding-bottom: 0.35rem;
    margin-bottom: 0.25rem;
}}
@media (prefers-color-scheme: dark) {{
    {_WAR_ROOM_MAIN_SELECTORS} div.st-key-war_room_spotlight_sticky {{
        background: linear-gradient(
            180deg,
            var(--background-color, #0e1117) 0%,
            var(--background-color, #0e1117) 92%,
            rgba(14, 17, 23, 0) 100%
        );
    }}
}}
</style>
"""

# Injected via components.html from the component iframe into the parent document.
WAR_ROOM_AGENT_SCROLL_HTML = """
<script>
(function () {
  const doc = window.parent.document;

  function mainScroller() {
    return (
      doc.querySelector('section[data-testid="stMain"]') ||
      doc.querySelector("section.main")
    );
  }

  function bringIntoView(el) {
    const stMain = mainScroller();
    if (!el) return;
    if (!stMain) {
      el.scrollIntoView({ behavior: "auto", block: "nearest", inline: "nearest" });
      return;
    }
    const padTop = 78;
    const padBot = 20;
    const er = el.getBoundingClientRect();
    const mr = stMain.getBoundingClientRect();
    if (er.top < mr.top + padTop) {
      stMain.scrollTop -= mr.top + padTop - er.top;
    }
    if (er.bottom > mr.bottom - padBot) {
      stMain.scrollTop += er.bottom - (mr.bottom - padBot);
    }
  }

  function run() {
    const stMain = mainScroller();
    const sp = doc.querySelector(".st-key-war_room_spotlight_sticky");
    if (sp) {
      const chats = sp.querySelectorAll('[data-testid="stChatMessage"]');
      const last = chats[chats.length - 1];
      if (last) {
        bringIntoView(last);
        return;
      }
      bringIntoView(sp);
      return;
    }
    if (stMain) {
      const all = stMain.querySelectorAll('[data-testid="stChatMessage"]');
      const tail = all[all.length - 1];
      if (tail) bringIntoView(tail);
    }
  }

  requestAnimationFrame(function () {
    requestAnimationFrame(function () {
      setTimeout(run, 0);
      setTimeout(run, 64);
    });
  });
})();
</script>
"""


def inject_war_room_compact_css() -> None:
    """Tighter vertical rhythm; sticky agent spotlight; chat blocks scroll into view cleanly."""
    st.markdown(WAR_ROOM_COMPACT_CSS, unsafe_allow_html=True)


def scroll_main_to_agent_focus() -> None:
    """Scroll the Streamlit **main** scrollport so the active spotlight chat is visible."""
    components.html(WAR_ROOM_AGENT_SCROLL_HTML, height=0, width=0)
