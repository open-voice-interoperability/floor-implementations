#!/usr/bin/env python3
"""Vercel entrypoint for the web-floor Flask gateway."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask_gateway import app as app
