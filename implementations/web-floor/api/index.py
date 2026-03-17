#!/usr/bin/env python3
"""Vercel entrypoint for the web-floor Flask gateway."""

try:
	from api.flask_gateway import app
except ModuleNotFoundError:
	from flask_gateway import app
