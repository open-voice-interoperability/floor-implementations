"""
Floor Management API endpoints per OFP 1.1.0
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Any
import structlog

from src.floor_manager.floor_control import FloorControl

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/floor", tags=["Floor Management"])

# Global floor control instance (in production, use dependency injection)
_floor_control: Optional[FloorControl] = None


def get_floor_control() -> FloorControl:
    """Get floor control instance"""
    global _floor_control
    if _floor_control is None:
        _floor_control = FloorControl()
    return _floor_control


async def _notify_floor_realtime(
    conversation_id: str,
    floor_control: FloorControl,
) -> None:
    """Push holder, queue, governance log, and metadata to SSE/WebSocket clients."""
    from src.api.websocket import broadcast_floor_update

    payload = await floor_control.build_realtime_payload(conversation_id)
    latest: Optional[dict[str, Any]] = None
    if payload.get("decisions"):
        latest = payload["decisions"][-1]
    await broadcast_floor_update(
        conversation_id,
        payload,
        latest_decision=latest,
    )


class FloorRequest(BaseModel):
    """Request floor model"""

    conversation_id: str
    speakerUri: str
    priority: int = 0
    reason: Optional[str] = None


class FloorRelease(BaseModel):
    """Release floor model"""

    conversation_id: str
    speakerUri: str


class FloorResponse(BaseModel):
    """Floor response model"""

    conversation_id: str
    granted: bool
    holder: Optional[str] = None
    queue_position: Optional[int] = None


class ConvenerAssign(BaseModel):
    """Assign or clear the optional Convener agent for a conversation."""

    conversation_id: str
    convener_speakerUri: Optional[str] = None


class FloorRevoke(BaseModel):
    """Revoke floor from a conversant (Convener or floor manager)."""

    conversation_id: str
    convener_speakerUri: str
    target_speakerUri: str
    reason: str = "@override"


class ConvenerNotice(BaseModel):
    """Record a Convener-authored governance message (OFP-style audit trail)."""

    conversation_id: str
    convener_speakerUri: str
    target_speakerUri: Optional[str] = None
    reason: str = "convener_notice"
    message: str = ""


@router.post("/request", response_model=FloorResponse)
async def request_floor(
    request: FloorRequest,
    floor_control: FloorControl = Depends(get_floor_control),
) -> FloorResponse:
    """
    Request floor for a conversation per OFP 1.1.0.

    Implements requestFloor-style behavior with optional reason for demos.
    """
    logger.info(
        "Floor request API",
        conversation_id=request.conversation_id,
        speakerUri=request.speakerUri,
    )

    granted = await floor_control.request_floor(
        request.conversation_id,
        request.speakerUri,
        request.priority,
        reason=request.reason,
    )

    holder = await floor_control.get_floor_holder(request.conversation_id)

    try:
        await _notify_floor_realtime(request.conversation_id, floor_control)
    except Exception:
        pass

    queue_pos: Optional[int] = None
    if not granted:
        queue = floor_control.get_request_queue(request.conversation_id)
        for i, item in enumerate(queue):
            if item["speakerUri"] == request.speakerUri:
                queue_pos = i + 1
                break

    return FloorResponse(
        conversation_id=request.conversation_id,
        granted=granted,
        holder=holder if granted else None,
        queue_position=queue_pos,
    )


@router.post("/release", response_model=dict)
async def release_floor(
    release: FloorRelease,
    floor_control: FloorControl = Depends(get_floor_control),
) -> dict:
    """
    Release floor for a conversation per OFP 1.1.0 (yieldFloor-style behavior).
    """
    logger.info(
        "Floor release API",
        conversation_id=release.conversation_id,
        speakerUri=release.speakerUri,
    )

    released = await floor_control.release_floor(
        release.conversation_id,
        release.speakerUri,
    )

    if not released:
        raise HTTPException(
            status_code=400,
            detail="Floor not held by this agent",
        )

    try:
        await _notify_floor_realtime(release.conversation_id, floor_control)
    except Exception:
        pass

    return {
        "conversation_id": release.conversation_id,
        "released": True,
    }


@router.post("/convener-notice", response_model=dict)
async def post_convener_notice(
    body: ConvenerNotice,
    floor_control: FloorControl = Depends(get_floor_control),
) -> dict:
    """
    Append a ``convenerNotice`` row to the floor governance log (no floor state change).

    Requires an assigned convener matching ``convener_speakerUri``.
    """
    ok = floor_control.record_convener_notice(
        body.conversation_id,
        body.convener_speakerUri,
        target_speaker_uri=body.target_speakerUri,
        reason=body.reason or "convener_notice",
        message=body.message or "",
    )
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Convener notice rejected (no convener assigned, or convener_speakerUri mismatch).",
        )
    try:
        await _notify_floor_realtime(body.conversation_id, floor_control)
    except Exception:
        pass
    return {
        "conversation_id": body.conversation_id,
        "recorded": True,
        "eventType": "convenerNotice",
    }


@router.post("/convener", response_model=dict)
async def assign_convener(
    body: ConvenerAssign,
    floor_control: FloorControl = Depends(get_floor_control),
) -> dict:
    """
    Assign or clear the Convener role for a conversation (OFP 1.1.0 Section 1.6.2).
    """
    await floor_control.assign_convener(
        body.conversation_id,
        body.convener_speakerUri,
    )
    try:
        await _notify_floor_realtime(body.conversation_id, floor_control)
    except Exception:
        pass
    return {
        "conversation_id": body.conversation_id,
        "convener_speakerUri": body.convener_speakerUri,
    }


@router.post("/revoke", response_model=dict)
async def revoke_floor_endpoint(
    body: FloorRevoke,
    floor_control: FloorControl = Depends(get_floor_control),
) -> dict:
    """
    Revoke floor from a conversant (OFP revokeFloor), mediated by convener when set.
    """
    ok = await floor_control.revoke_floor(
        body.conversation_id,
        body.convener_speakerUri,
        body.target_speakerUri,
        reason=body.reason,
    )
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Revoke not applied (convener mismatch, no holder, or wrong target)",
        )
    try:
        await _notify_floor_realtime(body.conversation_id, floor_control)
    except Exception:
        pass
    return {
        "conversation_id": body.conversation_id,
        "revoked": True,
        "target_speakerUri": body.target_speakerUri,
    }


@router.get("/decisions/{conversation_id}", response_model=dict)
async def list_floor_decisions(
    conversation_id: str,
    floor_control: FloorControl = Depends(get_floor_control),
) -> dict:
    """Return recent floor governance events for conference-style UIs."""
    return {
        "conversation_id": conversation_id,
        "decisions": floor_control.get_floor_decisions(conversation_id),
    }


@router.get("/holder/{conversation_id}", response_model=dict)
async def get_floor_holder(
    conversation_id: str,
    floor_control: FloorControl = Depends(get_floor_control),
) -> dict:
    """
    Get current floor holder and OFP conversation metadata.
    """
    holder = await floor_control.get_floor_holder(conversation_id)

    metadata = floor_control.get_conversation_metadata(conversation_id)

    return {
        "conversation_id": conversation_id,
        "holder": holder,
        "has_floor": holder is not None,
        "assignedFloorRoles": metadata.get("assignedFloorRoles"),
        "floorGranted": metadata.get("floorGranted"),
        "convener": floor_control.get_convener_uri(conversation_id),
        "decisions": floor_control.get_floor_decisions(conversation_id),
    }
