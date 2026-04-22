"""
WebSocket and SSE endpoints for real-time floor status updates
"""

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from typing import Set, Any, Optional
import json
import asyncio
from src.api.floor import get_floor_control
import structlog

logger = structlog.get_logger()

# Store active WebSocket connections
active_websockets: Set[WebSocket] = set()

# Store active SSE connections (conversation_id -> asyncio.Queue)
active_sse_queues: dict[str, asyncio.Queue] = {}


async def broadcast_floor_update(
    conversation_id: str,
    floor_status: dict[str, Any],
    *,
    latest_decision: Optional[dict[str, Any]] = None,
) -> None:
    """
    Broadcast floor status update to all connected clients.

    Optionally emits a separate ``floor_decision`` message for dual-channel UIs
    (public transcript vs governance log).

    Args:
        conversation_id: Conversation identifier
        floor_status: Floor status dictionary (holder, queue, decisions, metadata)
        latest_decision: Most recent governance line, if any
    """
    message = {
        "conversation_id": conversation_id,
        "type": "floor_update",
        "data": floor_status,
    }
    message_json = json.dumps(message)

    decision_message: Optional[dict[str, Any]] = None
    if latest_decision is not None:
        decision_message = {
            "conversation_id": conversation_id,
            "type": "floor_decision",
            "data": latest_decision,
        }

    # Broadcast to WebSocket connections
    disconnected = set()
    for websocket in active_websockets:
        try:
            await websocket.send_json(message)
            if decision_message is not None:
                await websocket.send_json(decision_message)
        except Exception as e:
            logger.warning("WebSocket send failed", error=str(e))
            disconnected.add(websocket)

    # Remove disconnected WebSockets
    active_websockets.difference_update(disconnected)

    # Broadcast to SSE connections
    if conversation_id in active_sse_queues:
        try:
            await active_sse_queues[conversation_id].put(message_json)
            if decision_message is not None:
                await active_sse_queues[conversation_id].put(
                    json.dumps(decision_message)
                )
        except Exception as e:
            logger.warning("SSE queue put failed", error=str(e))


async def websocket_floor_endpoint(websocket: WebSocket, conversation_id: str) -> None:
    """
    WebSocket endpoint for real-time floor status updates.
    
    Usage:
        ws://localhost:8000/ws/floor/{conversation_id}
    
    SECURITY NOTE: In production, add:
    - Origin validation (check websocket.headers.get("origin"))
    - Authentication token validation
    - Rate limiting per IP/user
    - Connection limits per conversation_id
    """
    # TODO: Add origin validation in production
    # origin = websocket.headers.get("origin")
    # if origin not in settings.CORS_ORIGINS:
    #     await websocket.close(code=1008, reason="Origin not allowed")
    #     return
    
    # TODO: Add authentication token validation in production
    # token = websocket.query_params.get("token")
    # if not validate_token(token):
    #     await websocket.close(code=1008, reason="Authentication required")
    #     return
    
    await websocket.accept()
    active_websockets.add(websocket)
    
    try:
        # Send initial floor status
        floor_control = get_floor_control()
        payload = await floor_control.build_realtime_payload(conversation_id)

        await websocket.send_json(
            {
                "type": "initial_status",
                "conversation_id": conversation_id,
                "holder": payload["holder"],
                "queue": payload["queue"],
                "decisions": payload["decisions"],
                "assignedFloorRoles": payload["assignedFloorRoles"],
                "floorGranted": payload["floorGranted"],
                "convener": payload["convener"],
            }
        )
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for client message (ping/pong or close)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
                elif data == "close":
                    break
                    
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat"})
                
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected", conversation_id=conversation_id)
    except Exception as e:
        logger.error("WebSocket error", error=str(e), conversation_id=conversation_id)
    finally:
        active_websockets.discard(websocket)


async def sse_event_generator(conversation_id: str):
    """
    Server-Sent Events generator for floor status updates.
    
    Usage:
        GET /events/floor/{conversation_id}
    
    SECURITY NOTE: In production, add:
    - Request origin validation
    - Authentication token validation
    - Rate limiting per IP/user
    - Connection limits per conversation_id
    """
    # Create queue for this conversation
    queue = asyncio.Queue()
    active_sse_queues[conversation_id] = queue
    
    try:
        # Send initial status
        floor_control = get_floor_control()
        payload = await floor_control.build_realtime_payload(conversation_id)

        initial_data = json.dumps(
            {
                "type": "initial_status",
                "conversation_id": conversation_id,
                "holder": payload["holder"],
                "queue": payload["queue"],
                "decisions": payload["decisions"],
                "assignedFloorRoles": payload["assignedFloorRoles"],
                "floorGranted": payload["floorGranted"],
                "convener": payload["convener"],
            }
        )
        yield f"data: {initial_data}\n\n"
        
        # Keep connection alive and send updates
        while True:
            try:
                # Wait for update (with timeout for heartbeat)
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {message}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat
                    heartbeat = json.dumps({"type": "heartbeat"})
                    yield f"data: {heartbeat}\n\n"
                    
            except Exception as e:
                logger.error("SSE generator error", error=str(e))
                break
                
    finally:
        # Cleanup
        if conversation_id in active_sse_queues:
            del active_sse_queues[conversation_id]


def create_sse_endpoint(router):
    """
    Create SSE endpoint and add to router.
    
    Args:
        router: FastAPI router instance
    """
    @router.get("/events/floor/{conversation_id}", tags=["Real-Time"])
    async def sse_floor_events(conversation_id: str):
        """
        Server-Sent Events endpoint for real-time floor status.
        
        Usage in browser:
            const eventSource = new EventSource('http://localhost:8000/api/v1/events/floor/conv_001');
            eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                console.log('Floor update:', data);
            };
        """
        return StreamingResponse(
            sse_event_generator(conversation_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable buffering for nginx
            }
        )


def create_websocket_endpoint(app):
    """
    Create WebSocket endpoint and add to FastAPI app.
    
    Args:
        app: FastAPI application instance
    """
    @app.websocket("/ws/floor/{conversation_id}")
    async def websocket_floor_status(websocket: WebSocket, conversation_id: str):
        """
        WebSocket endpoint for real-time floor status updates.
        
        Usage in browser:
            const ws = new WebSocket('ws://localhost:8000/ws/floor/conv_001');
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                console.log('Floor update:', data);
            };
            ws.send('ping');  // Keep connection alive
        """
        await websocket_floor_endpoint(websocket, conversation_id)

