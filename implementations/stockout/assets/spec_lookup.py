"""
Single-shot OFP spec title fetch for conference demos.

Designed for one visible "expert witness" moment: short timeout, plain fallback.
Not a full MCP client; callable from Streamlit or CLI.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Optional

import httpx

SPEC_URL = (
    "https://raw.githubusercontent.com/open-voice-interoperability/openfloor-docs/"
    "main/specifications/ConversationEnvelope/1.1.0/InteroperableConvEnvSpec.md"
)

_CACHE_PATH = Path(__file__).resolve().parent / ".spec_title_cache.txt"


def _extract_title(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return re.sub(r"^#+\s*", "", stripped)[:200]
    return text.strip()[:200]


async def fetch_spec_heading(timeout_seconds: float = 3.0) -> str:
    """
    Fetch the beginning of the official OFP envelope spec and return a title line.

    Args:
        timeout_seconds: Hard cap for the HTTP round-trip.

    Returns:
        A short human-readable string; never raises for network errors.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(SPEC_URL)
            response.raise_for_status()
            snippet = response.text[:4000]
            title = _extract_title(snippet)
            try:
                _CACHE_PATH.write_text(title, encoding="utf-8")
            except OSError:
                pass
            return title
    except Exception:
        cached = _read_cache()
        if cached:
            return f"{cached} (cached; live fetch failed)"
        return "OFP 1.1.0 spec: offline (no cache). See openfloor-docs on GitHub."


def _read_cache() -> Optional[str]:
    try:
        t = _CACHE_PATH.read_text(encoding="utf-8").strip()
        return t or None
    except OSError:
        return None


def fetch_spec_heading_sync(timeout_seconds: float = 3.0) -> str:
    """Sync wrapper for Streamlit and simple CLIs."""
    return asyncio.run(fetch_spec_heading(timeout_seconds=timeout_seconds))


if __name__ == "__main__":
    print(fetch_spec_heading_sync())
