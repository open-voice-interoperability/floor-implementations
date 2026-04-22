"""Shared typewriter iframe for LLM assistant lines (home + LLM page)."""

from __future__ import annotations

import hashlib
import json

import streamlit.components.v1 as components


def typewriter_storage_key(
    epoch: int,
    idx: int,
    timestamp: str,
    content: str,
    *,
    namespace: str,
) -> str:
    """Stable key for localStorage. `namespace=\"llmwr\"` matches the original LLM page hash input."""
    raw = (
        f"{epoch}|{idx}|{timestamp}|{content}"
        if namespace == "llmwr"
        else f"{namespace}|{epoch}|{idx}|{timestamp}|{content}"
    )
    h = hashlib.sha256(raw.encode()).hexdigest()[:28]
    return f"stockout_llm_tw_{h}"


def render_typewriter_iframe(
    text: str,
    *,
    storage_key: str,
    ms_per_char: int = 14,
) -> None:
    """Character-at-a-time reveal in an iframe; completion stored in localStorage (survives Streamlit reruns)."""
    text_js = json.dumps(text)
    key_js = json.dumps(storage_key)
    # Tight height: less empty chrome between stacked agent replies.
    h = min(360, max(64, len(text) // 56 * 17 + 36))
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
body {{ margin:0; padding:2px 2px; font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  font-size:0.92rem; line-height:1.45; color: #1a1a1a; background: transparent; }}
@media (prefers-color-scheme: dark) {{
  body {{ color: #e2e8f0; }}
}}
#out {{ white-space: pre-wrap; word-break: break-word; min-height: 1.1rem; }}
</style></head><body>
<div id="out"></div>
<script>
(function() {{
  const full = {text_js};
  const k = {key_js};
  const speed = {ms_per_char};
  const el = document.getElementById("out");
  function scrollParentToIframe() {{
    try {{
      const fe = window.frameElement;
      if (!fe || typeof fe.getBoundingClientRect !== "function") return;
      const r = fe.getBoundingClientRect();
      const vh = (window.parent && window.parent.innerHeight) ? window.parent.innerHeight : 800;
      if (r.bottom > vh - 56) {{
        fe.scrollIntoView({{ block: "end", behavior: "auto", inline: "nearest" }});
      }}
    }} catch (e) {{}}
  }}
  try {{
    if (localStorage.getItem(k) === "done") {{
      el.textContent = full;
      scrollParentToIframe();
      return;
    }}
  }} catch (e) {{}}
  let i = 0;
  function tick() {{
    if (i > full.length) {{
      try {{ localStorage.setItem(k, "done"); }} catch (e) {{}}
      scrollParentToIframe();
      return;
    }}
    el.textContent = full.slice(0, i);
    i++;
    if (i % 10 === 0 || i >= full.length) {{
      scrollParentToIframe();
    }}
    setTimeout(tick, speed);
  }}
  tick();
}})();
</script>
</body></html>"""
    components.html(html, height=h, scrolling=False)
