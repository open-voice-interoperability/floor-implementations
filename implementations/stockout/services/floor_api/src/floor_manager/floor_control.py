"""
Floor Control - Floor Manager's floor control logic per OFP 1.1.0

This implements the Floor Manager's floor control logic (minimal behaviors per Section 2.2).
The floor operates as an autonomous state machine.

NOTE: "Convener" in OFP spec refers to an optional AGENT that mediates conversations,
      not this component. This is the Floor Manager's built-in floor control logic.
"""

from datetime import datetime, timedelta, UTC
from typing import Optional, Dict, Any, List
from enum import Enum
import structlog

from src.config import settings

logger = structlog.get_logger()

_MAX_DECISION_LOG = 50


class FloorState(Enum):
    """Floor state enumeration"""
    IDLE = "idle"
    GRANTED = "granted"
    REQUESTED = "requested"
    RELEASED = "released"


class FloorControl:
    """
    Floor Manager's floor control logic per OFP 1.1.0
    
    Implements minimal floor management behaviors (OFP Spec Section 2.2):
    - requestFloor → grantFloor logic (with priority queue)
    - yieldFloor → next agent logic
    - Floor state as autonomous state machine
    - Agents request/yield floor, Floor Manager makes decisions
    
    NOTE: This is NOT the "Convener" from OFP spec. The spec's "Convener" 
          is an optional AGENT that mediates conversations. This is the 
          Floor Manager's built-in floor control logic.
    """

    def __init__(self, floor_manager_speakerUri: Optional[str] = None) -> None:
        """
        Initialize floor control logic
        
        Args:
            floor_manager_speakerUri: Speaker URI of the Floor Manager
                                      If None, uses default from settings
        """
        self._floor_holders: dict[str, dict] = {}
        self._floor_requests: dict[str, list] = {}
        self._floor_timeout = settings.FLOOR_TIMEOUT
        self._max_hold_time = settings.FLOOR_MAX_HOLD_TIME
        # Floor Manager identification per OFP 1.1.0
        # Note: If an optional Convener Agent exists, it would be tracked in assignedFloorRoles
        self.floor_manager_speakerUri = floor_manager_speakerUri or "tag:floor.manager,2025:manager"
        self._conversation_metadata: dict[str, dict] = {}  # Track conversation metadata
        self._floor_decisions: dict[str, List[Dict[str, Any]]] = {}

    def _record_decision(
        self,
        conversation_id: str,
        event_type: str,
        speaker_uri: str,
        *,
        reason: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Append an OFP-style floor governance line for demos and audits."""
        entry: Dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "eventType": event_type,
            "speakerUri": speaker_uri,
        }
        if reason is not None:
            entry["reason"] = reason
        if detail is not None:
            entry["detail"] = detail
        log = self._floor_decisions.setdefault(conversation_id, [])
        log.append(entry)
        if len(log) > _MAX_DECISION_LOG:
            del log[0 : len(log) - _MAX_DECISION_LOG]
        return entry

    def get_floor_decisions(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Return recent floor governance events (newest last)."""
        return list(self._floor_decisions.get(conversation_id, []))

    def get_request_queue(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Return pending floor requests for API and real-time clients."""
        raw = self._floor_requests.get(conversation_id) or []
        return [
            {"speakerUri": r["speakerUri"], "priority": r["priority"]}
            for r in raw
        ]

    async def build_realtime_payload(self, conversation_id: str) -> Dict[str, Any]:
        """Snapshot for SSE/WebSocket: holder, queue, governance log, OFP metadata."""
        holder = await self.get_floor_holder(conversation_id)
        meta = self.get_conversation_metadata(conversation_id)
        return {
            "holder": holder,
            "queue": self.get_request_queue(conversation_id),
            "decisions": self.get_floor_decisions(conversation_id),
            "assignedFloorRoles": meta.get("assignedFloorRoles"),
            "floorGranted": meta.get("floorGranted"),
            "convener": self.get_convener_uri(conversation_id),
        }

    async def assign_convener(
        self,
        conversation_id: str,
        convener_speaker_uri: Optional[str],
    ) -> None:
        """
        Set or clear the optional Convener agent for a conversation.

        When set, ``assignedFloorRoles.convener`` is published in metadata
        per OFP 1.1.0 Section 1.6.2.
        """
        meta = self._conversation_metadata.setdefault(
            conversation_id,
            {"assignedFloorRoles": {}},
        )
        roles = meta.setdefault("assignedFloorRoles", {})
        if convener_speaker_uri:
            roles["convener"] = [convener_speaker_uri]
            self._record_decision(
                conversation_id,
                "assignConvener",
                convener_speaker_uri,
                detail="convener_role_bound",
            )
        else:
            roles.pop("convener", None)
            self._record_decision(
                conversation_id,
                "clearConvener",
                self.floor_manager_speakerUri,
                detail="convener_role_cleared",
            )

    def get_convener_uri(self, conversation_id: str) -> Optional[str]:
        """Return the convener speakerUri if exactly one is assigned."""
        meta = self._conversation_metadata.get(conversation_id, {})
        roles = meta.get("assignedFloorRoles") or {}
        uris = roles.get("convener") or []
        if len(uris) == 1:
            return uris[0]
        return None

    def record_convener_notice(
        self,
        conversation_id: str,
        convener_speaker_uri: str,
        *,
        target_speaker_uri: Optional[str] = None,
        reason: str = "convener_notice",
        message: str = "",
    ) -> bool:
        """
        Append a governance log line for a Convener-authored notice (demo / audit).

        The caller must use the same ``convener_speaker_uri`` as the role assigned
        for this conversation. The notice does not change floor holder state.
        """
        assigned = self.get_convener_uri(conversation_id)
        if assigned is None or assigned != convener_speaker_uri:
            return False
        body = (message or "").strip()
        if len(body) > 1200:
            body = body[:1197] + "..."
        detail = body
        if target_speaker_uri:
            detail = f"to={target_speaker_uri}\n{body}"
        self._record_decision(
            conversation_id,
            "convenerNotice",
            convener_speaker_uri,
            reason=reason,
            detail=detail,
        )
        return True

    async def revoke_floor(
        self,
        conversation_id: str,
        convener_speaker_uri: str,
        target_speaker_uri: str,
        reason: str = "@override",
    ) -> bool:
        """
        Revoke floor from a conversant (Convener or policy actor).

        Verifies ``convener_speaker_uri`` matches the assigned convener when
        one is set; otherwise allows the floor manager identity to revoke.
        """
        assigned = self.get_convener_uri(conversation_id)
        if assigned is not None:
            if convener_speaker_uri != assigned:
                return False
        else:
            if convener_speaker_uri != self.floor_manager_speakerUri:
                return False
        if conversation_id not in self._floor_holders:
            return False
        holder = self._floor_holders[conversation_id]["speakerUri"]
        if holder != target_speaker_uri:
            return False
        # _revoke_floor records revokeFloor and promotes queue
        await self._revoke_floor(conversation_id, reason=reason)
        return True

    async def request_floor(
        self,
        conversation_id: str,
        speakerUri: str,
        priority: int = 0,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Request floor for a conversation per OFP 1.1.0 Section 1.19
        
        Implements minimal Floor Manager behavior (Spec Section 2.2):
        - If floor available: grant immediately
        - If not: queue request by priority
        
        Floor Manager makes the decision autonomously.

        Args:
            conversation_id: Unique conversation identifier
            speakerUri: Speaker URI requesting the floor
            priority: Request priority (higher = more priority)
            reason: Optional OFP-style reason for requestFloor (demo / audit)

        Returns:
            True if floor granted immediately, False if queued
        """
        logger.info(
            "Floor request received by Floor Manager",
            conversation_id=conversation_id,
            speakerUri=speakerUri,
            priority=priority,
            floor_manager=self.floor_manager_speakerUri
        )

        # Initialize conversation metadata if needed
        if conversation_id not in self._conversation_metadata:
            self._conversation_metadata[conversation_id] = {
                # Note: assignedFloorRoles can include "convener" if a Convener Agent exists
                # For now, we only track the Floor Manager
                "assignedFloorRoles": {}
            }

        self._record_decision(
            conversation_id,
            "requestFloor",
            speakerUri,
            reason=reason,
            detail="queued" if conversation_id in self._floor_holders else "floor_idle",
        )

        # Check if floor is available (Floor Manager decision)
        if conversation_id not in self._floor_holders:
            await self._grant_floor(conversation_id, speakerUri);
            convener = self.get_convener_uri(conversation_id)
            self._record_decision(
                conversation_id,
                "grantFloor",
                speakerUri,
                reason=reason,
                detail="via_convener" if convener else "no_convener_minimal_behavior",
            )
            return True

        # Add to request queue (Floor Manager will process later)
        if conversation_id not in self._floor_requests:
            self._floor_requests[conversation_id] = []

        request = {
            "speakerUri": speakerUri,
            "priority": priority,
            "timestamp": datetime.now(UTC)
        }
        self._floor_requests[conversation_id].append(request);
        self._floor_requests[conversation_id].sort(
            key=lambda x: (-x["priority"], x["timestamp"])
        );

        return False

    async def release_floor(self, conversation_id: str, speakerUri: str) -> bool:
        """
        Release floor for a conversation per OFP 1.1.0 Section 1.22 (yieldFloor)
        
        Implements minimal Floor Manager behavior (Spec Section 2.2):
        - Release floor from current holder
        - Grant floor to next agent in queue (if any)

        Args:
            conversation_id: Unique conversation identifier
            speakerUri: Speaker URI releasing the floor

        Returns:
            True if floor was released, False if agent didn't hold floor
        """
        logger.info(
            "Floor yield received by Floor Manager",
            conversation_id=conversation_id,
            speakerUri=speakerUri,
            floor_manager=self.floor_manager_speakerUri
        )

        if conversation_id not in self._floor_holders:
            return False

        holder = self._floor_holders[conversation_id];
        if holder["speakerUri"] != speakerUri:
            return False

        self._record_decision(
            conversation_id,
            "yieldFloor",
            speakerUri,
            reason="@complete",
            detail="holder_released",
        )

        del self._floor_holders[conversation_id];
        
        # Clear floorGranted in conversation metadata
        if conversation_id in self._conversation_metadata:
            self._conversation_metadata[conversation_id].pop("floorGranted", None);

        # Floor Manager grants floor to next requester in queue
        await self._process_queue(conversation_id);

        return True

    async def get_floor_holder(self, conversation_id: str) -> Optional[str]:
        """
        Get current floor holder for a conversation

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            Speaker URI holding the floor, or None
        """
        if conversation_id not in self._floor_holders:
            return None

        holder = self._floor_holders[conversation_id];
        # Check if floor grant has expired
        if datetime.now(UTC) - holder["granted_at"] > timedelta(
            seconds=self._max_hold_time
        ):
            await self._revoke_floor(conversation_id, reason="@timeout");
            return None

        return holder["speakerUri"]

    async def _grant_floor(self, conversation_id: str, speakerUri: str) -> None:
        """
        Grant floor to an agent per OFP 1.1.0 Section 1.20 (grantFloor)
        
        Floor Manager decision. Updates floorGranted in conversation metadata.
        
        Per OFP 1.1.0: floorGranted is an array of speakerURIs with floor rights.
        """
        granted_at = datetime.now(UTC);
        self._floor_holders[conversation_id] = {
            "speakerUri": speakerUri,
            "granted_at": granted_at
        };
        
        # Update conversation metadata with floorGranted per OFP 1.1.0
        if conversation_id not in self._conversation_metadata:
            self._conversation_metadata[conversation_id] = {
                "assignedFloorRoles": {}  # Can include convener if Convener Agent present
            };
        
        # OFP 1.1.0: floorGranted is an array of speakerURIs (simplified from 1.0.1)
        self._conversation_metadata[conversation_id]["floorGranted"] = [speakerUri];
        
        logger.info(
            "Floor granted by Floor Manager",
            conversation_id=conversation_id,
            speakerUri=speakerUri,
            floor_manager=self.floor_manager_speakerUri,
            granted_at=granted_at
        );

    async def _revoke_floor(self, conversation_id: str, reason: str = "@timeout") -> None:
        """
        Revoke floor due to timeout or other reason per OFP 1.1.0 Section 1.21 (revokeFloor)
        
        Floor Manager decision (e.g., timeout, override).
        """
        if conversation_id in self._floor_holders:
            speakerUri = self._floor_holders[conversation_id]["speakerUri"];
            del self._floor_holders[conversation_id];
            
            # Clear floorGranted in conversation metadata
            if conversation_id in self._conversation_metadata:
                self._conversation_metadata[conversation_id].pop("floorGranted", None);
            
            logger.warning(
                "Floor revoked by Floor Manager",
                conversation_id=conversation_id,
                speakerUri=speakerUri,
                reason=reason,
                floor_manager=self.floor_manager_speakerUri
            );
            self._record_decision(
                conversation_id,
                "revokeFloor",
                speakerUri,
                reason=reason,
                detail="timeout_or_manager_revoke",
            )
            await self._process_queue(conversation_id);
    
    def get_conversation_metadata(self, conversation_id: str) -> Dict[str, Any]:
        """
        Get conversation metadata including assignedFloorRoles and floorGranted
        
        Returns metadata per OFP 1.1.0 Section 1.6 (conversation object structure).
        
        Note: 
        - assignedFloorRoles: Dict[str, List[str]] mapping roles to arrays of speakerURIs
        - floorGranted: List[str] of speakerURIs with floor rights
        - assignedFloorRoles can include "convener" key if a Convener Agent
          (per OFP spec) is participating. Currently not implemented.
        """
        return self._conversation_metadata.get(conversation_id, {
            "assignedFloorRoles": {}  # Empty by default, can be populated if Convener Agent exists
        });

    async def _process_queue(self, conversation_id: str) -> None:
        """Process floor request queue"""
        if (
            conversation_id not in self._floor_requests
            or not self._floor_requests[conversation_id]
        ):
            return

        next_request = self._floor_requests[conversation_id].pop(0);
        await self._grant_floor(conversation_id, next_request["speakerUri"]);
        convener = self.get_convener_uri(conversation_id)
        self._record_decision(
            conversation_id,
            "grantFloor",
            next_request["speakerUri"],
            detail="via_convener" if convener else "queue_promoted",
        )

        if not self._floor_requests[conversation_id]:
            del self._floor_requests[conversation_id];

