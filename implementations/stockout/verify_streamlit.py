#!/usr/bin/env python3
"""Streamlit smoke test (AppTest). From repo root: `python verify_streamlit.py`."""

from __future__ import annotations

import sys

from streamlit.testing.v1 import AppTest


def main() -> int:
    paths = ("app.py", "pages/2_Floor_decisions_log.py", "pages/3_LLM_war_room.py")
    for path in paths:
        at = AppTest.from_file(path, default_timeout=120)
        at.run(timeout=120)
        if len(at.exception):
            print(f"FAIL {path}: {at.exception[0]}", file=sys.stderr)
            return 1
        if len(at.error):
            print(f"FAIL {path}: st.error count={len(at.error)}", file=sys.stderr)
            return 1
        print(f"OK   {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
