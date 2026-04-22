"""
Collaborative Floor Passing Pattern per OFP 1.0.0

Agents negotiate floor autonomously via requestFloor/yieldFloor, with a minimal
floor manager that only arbitrates conflicts. Supports emergent behavior and
self-organization of agents.
"""

from typing import Optional
import structlog

from src.floor_manager.floor_control import FloorControl
from src.floor_manager.envelope import EventType

logger = structlog.get_logger()


class CollaborativeOrchestrator:
    """
    Collaborative Floor Passing per OFP 1.0.0
    
    Agents negotiate floor autonomously, floor manager only arbitrates conflicts
    """

    def __init__(self, floor_control: FloorControl) -> None:
        """
        Initialize collaborative orchestrator

        Args:
            floor_control: Floor control instance
        """
        self.floor_control = floor_control

    async def handle_floor_request(
        self,
        conversation_id: str,
        speakerUri: str,
        priority: int = 0
    ) -> bool:
        """
        Handle autonomous floor request from agent

        Args:
            conversation_id: Conversation identifier
            speakerUri: Agent requesting floor
            priority: Request priority

        Returns:
            True if granted immediately, False if queued
        """
        granted = await self.floor_control.request_floor(
            conversation_id,
            speakerUri,
            priority
        );

        if granted:
            logger.info(
                "Floor granted autonomously",
                conversation_id=conversation_id,
                speakerUri=speakerUri
            );
        else:
            logger.info(
                "Floor request queued",
                conversation_id=conversation_id,
                speakerUri=speakerUri
            );

        return granted

    async def handle_floor_yield(
        self,
        conversation_id: str,
        speakerUri: str,
        reason: str = "@complete"
    ) -> bool:
        """
        Handle floor yield from agent

        Args:
            conversation_id: Conversation identifier
            speakerUri: Agent yielding floor
            reason: Reason for yielding

        Returns:
            True if yielded successfully
        """
        released = await self.floor_control.release_floor(
            conversation_id,
            speakerUri
        );

        if released:
            logger.info(
                "Floor yielded",
                conversation_id=conversation_id,
                speakerUri=speakerUri,
                reason=reason
            );

        return released

    async def arbitrate_conflict(
        self,
        conversation_id: str,
        requesters: list[tuple[str, int]]
    ) -> Optional[str]:
        """
        Arbitrate floor conflict between multiple requesters

        Args:
            conversation_id: Conversation identifier
            requesters: List of (speakerUri, priority) tuples

        Returns:
            Speaker URI of winner, or None
        """
        if not requesters:
            return None;

        # Sort by priority (higher first)
        sorted_requesters = sorted(requesters, key=lambda x: -x[1]);
        winner = sorted_requesters[0][0];

        logger.info(
            "Floor conflict arbitrated",
            conversation_id=conversation_id,
            winner=winner,
            total_requesters=len(requesters)
        );

        return winner

