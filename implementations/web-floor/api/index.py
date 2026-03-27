#!/usr/bin/env python3
"""Vercel entrypoint for the web-floor Flask gateway."""

import sys
from pathlib import Path

# Ensure sibling modules are importable
api_dir = Path(__file__).parent
if str(api_dir) not in sys.path:
	sys.path.insert(0, str(api_dir))

from flask_gateway import app

__all__ = ["app"]
