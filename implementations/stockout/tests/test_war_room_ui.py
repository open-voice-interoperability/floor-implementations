"""Regression: scroll + compact CSS must target Streamlit 1.40+ main scrollport (stMain)."""

from __future__ import annotations

import war_room_ui


def test_scroll_js_queries_st_main_before_section_main() -> None:
    html = war_room_ui.WAR_ROOM_AGENT_SCROLL_HTML
    assert 'data-testid="stMain"' in html
    assert "section.main" in html
    assert "st-key-war_room_spotlight_sticky" in html


def test_compact_css_targets_st_main_and_legacy_main() -> None:
    css = war_room_ui.WAR_ROOM_COMPACT_CSS
    assert 'data-testid="stMain"' in css
    assert "section.main" in css
    assert "st-key-war_room_spotlight_sticky" in css
