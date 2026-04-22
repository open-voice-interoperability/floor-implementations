"""
FastAPI application entry point for Open Floor Protocol
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog
import logging

from src.config import settings
from src.api import floor_router, envelope_router
from src.api.websocket import create_sse_endpoint, create_websocket_endpoint

# Convert LOG_LEVEL string to logging level
LOG_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
log_level = LOG_LEVEL_MAP.get(settings.LOG_LEVEL.upper(), logging.INFO)

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(log_level),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)

logger = structlog.get_logger()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Open Floor Protocol 1.1 Multi-Agent System",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(floor_router)
app.include_router(envelope_router)
# Note: Agent registry removed - not part of OFP 1.1 specification

# Add real-time endpoints (SSE and WebSocket)
create_sse_endpoint(floor_router)  # SSE endpoint for one-way updates
create_websocket_endpoint(app)  # WebSocket endpoint for bidirectional updates


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize services on startup"""
    logger.info("Starting Open Floor Protocol API", version=settings.APP_VERSION)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cleanup on shutdown"""
    logger.info("Shutting down Open Floor Protocol API")


@app.get("/")
async def root() -> dict:
    """Root endpoint"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running"
    }


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint"""
    return {"status": "healthy"}

