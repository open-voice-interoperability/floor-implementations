"""
Conversation Envelope API endpoints per OFP 1.0.1

Per OFP 1.0.1: Envelope routing is part of Floor Manager, not a separate component.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any
import structlog

from src.floor_manager.manager import FloorManager
from src.floor_manager.envelope import (
    OpenFloorEnvelope,
    EventType,
    EventObject,
    ToObject
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/envelopes", tags=["Envelope Processing"])

# Global Floor Manager instance (in production, use dependency injection)
_floor_manager: Optional[FloorManager] = None


def get_floor_manager() -> FloorManager:
    """
    Get Floor Manager instance
    
    Per OFP 1.0.1: Floor Manager includes envelope routing
    """
    global _floor_manager
    if _floor_manager is None:
        _floor_manager = FloorManager();
    return _floor_manager


class SendEnvelopeRequest(BaseModel):
    """Send envelope request model"""
    envelope: Dict[str, Any]  # OpenFloorEnvelope as dict


class SendUtteranceRequest(BaseModel):
    """Send utterance request model"""
    conversation_id: str
    sender_speakerUri: str
    sender_serviceUrl: Optional[str] = None
    target_speakerUri: Optional[str] = None
    target_serviceUrl: Optional[str] = None
    text: str
    private: bool = False


@router.post("/send", response_model=dict)
async def send_envelope(
    request: SendEnvelopeRequest,
    floor_manager: FloorManager = Depends(get_floor_manager)
) -> dict:
    """
    Send a conversation envelope per OFP 1.0.1
    
    Accepts full OpenFloorEnvelope JSON structure.
    Floor Manager processes and routes the envelope.
    """
    try:
        envelope = OpenFloorEnvelope.from_dict(request.envelope);
        logger.info(
            "Sending envelope",
            conversation_id=envelope.conversation.id,
            sender=envelope.sender.speakerUri,
            event_count=len(envelope.events)
        );

        success = await floor_manager.process_envelope(envelope);

        if not success:
            raise HTTPException(
                status_code=400,
                detail="Failed to process envelope"
            );

        return {
            "success": True,
            "conversation_id": envelope.conversation.id,
            "events_processed": len(envelope.events)
        };
    except Exception as e:
        logger.error("Error sending envelope", error=str(e));
        # Don't expose internal error details to clients
        raise HTTPException(
            status_code=400,
            detail="Failed to process envelope. Please check envelope format and try again."
        );


@router.post("/utterance", response_model=dict)
async def send_utterance(
    request: SendUtteranceRequest,
    floor_manager: FloorManager = Depends(get_floor_manager)
) -> dict:
    """
    Send an utterance event per OFP 1.0.1
    
    Simplified endpoint for sending text utterances.
    Floor Manager processes and routes the utterance.
    """
    logger.info(
        "Sending utterance",
        conversation_id=request.conversation_id,
        sender=request.sender_speakerUri,
        target=request.target_speakerUri
    );

    envelope = await floor_manager.send_utterance(
        conversation_id=request.conversation_id,
        sender_speakerUri=request.sender_speakerUri,
        sender_serviceUrl=request.sender_serviceUrl,
        target_speakerUri=request.target_speakerUri,
        target_serviceUrl=request.target_serviceUrl,
        text=request.text,
        private=request.private
    );

    return {
        "success": True,
        "conversation_id": envelope.conversation.id,
        "envelope": envelope.to_dict()
    };


@router.post("/validate", response_model=dict)
async def validate_envelope(
    envelope: Dict[str, Any]
) -> dict:
    """
    Validate an envelope against OFP 1.0.1 schema
    """
    try:
        ofp_envelope = OpenFloorEnvelope.from_dict(envelope);
        return {
            "valid": True,
            "version": ofp_envelope.schema_obj.version,
            "conversation_id": ofp_envelope.conversation.id
        };
    except Exception as e:
        # Log full error server-side, return generic message to client
        logger.error("Envelope validation failed", error=str(e));
        return {
            "valid": False,
            "error": "Invalid envelope format. Please check the envelope structure."
        };

