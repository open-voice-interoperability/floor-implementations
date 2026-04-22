"""
API Routers for Open Floor Protocol 1.0.1

Per OFP 1.0.1:
- Agent registry removed (not in specification)
- Envelope routing is part of Floor Manager
"""

from src.api.floor import router as floor_router
from src.api.envelope import router as envelope_router

__all__ = ["floor_router", "envelope_router"]

