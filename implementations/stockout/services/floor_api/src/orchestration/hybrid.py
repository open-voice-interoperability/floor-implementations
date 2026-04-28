"""
Hybrid Delegation Model per OFP 1.0.1

A master agent maintains primary floor and temporarily delegates to specialist
agents via sub-conversations, maintaining overall control and context.
Ideal for complex tasks requiring diverse expertise.

NOTE: Per OFP 1.0.1, no agent registry exists. Agents are identified only
      by their speakerUri in envelopes.
"""

from typing import Optional, Dict, List
import structlog

from src.floor_manager.floor_control import FloorControl
# Note: Agent registry removed per OFP 1.0.1
from src.floor_manager.envelope import OpenFloorEnvelope

logger = structlog.get_logger()


class HybridOrchestrator:
    """
    Hybrid Delegation Model per OFP 1.0.0
    
    Master agent delegates to specialists while maintaining overall control
    """

    def __init__(
        self,
        master_speakerUri: str,
        floor_control: FloorControl
    ) -> None:
        """
        Initialize hybrid orchestrator

        Args:
            master_speakerUri: Master agent speaker URI
            floor_control: Floor control instance
        
        Note: No agent registry needed per OFP 1.0.1 - agents are identified
              only by their speakerUri in envelopes.
        """
        self.master_speakerUri = master_speakerUri;
        self.floor_control = floor_control;
        self._delegations: Dict[str, dict] = {}  # conversation_id -> delegation info

    async def delegate_to_specialist(
        self,
        main_conversation_id: str,
        specialist_speakerUri: str,
        sub_task_description: str
    ) -> str:
        """
        Delegate a sub-task to a specialist agent

        Args:
            main_conversation_id: Main conversation identifier
            specialist_speakerUri: Specialist agent speaker URI
            sub_task_description: Description of sub-task

        Returns:
            Sub-conversation identifier
        """
        # Create sub-conversation ID
        sub_conversation_id = f"{main_conversation_id}_sub_{specialist_speakerUri}";

        # Grant floor to specialist in sub-conversation
        await self.floor_control.request_floor(
            sub_conversation_id,
            specialist_speakerUri,
            priority=10  # High priority for delegation
        );

        # Track delegation
        self._delegations[sub_conversation_id] = {
            "main_conversation_id": main_conversation_id,
            "specialist_speakerUri": specialist_speakerUri,
            "task_description": sub_task_description,
            "status": "active"
        };

        logger.info(
            "Task delegated to specialist",
            main_conversation_id=main_conversation_id,
            sub_conversation_id=sub_conversation_id,
            specialist=specialist_speakerUri
        );

        return sub_conversation_id

    async def recall_delegation(
        self,
        sub_conversation_id: str
    ) -> bool:
        """
        Recall delegation and return control to master

        Args:
            sub_conversation_id: Sub-conversation identifier

        Returns:
            True if recalled successfully
        """
        if sub_conversation_id not in self._delegations:
            return False;

        delegation = self._delegations[sub_conversation_id];
        specialist_speakerUri = delegation["specialist_speakerUri"];

        # Revoke floor from specialist
        await self.floor_control.release_floor(
            sub_conversation_id,
            specialist_speakerUri
        );

        # Update delegation status
        delegation["status"] = "recalled";

        logger.info(
            "Delegation recalled",
            sub_conversation_id=sub_conversation_id,
            specialist=specialist_speakerUri
        );

        return True

    async def merge_sub_conversation(
        self,
        sub_conversation_id: str,
        result: dict
    ) -> bool:
        """
        Merge sub-conversation results back into main conversation

        Args:
            sub_conversation_id: Sub-conversation identifier
            result: Results from sub-conversation

        Returns:
            True if merged successfully
        """
        if sub_conversation_id not in self._delegations:
            return False;

        delegation = self._delegations[sub_conversation_id];
        delegation["result"] = result;
        delegation["status"] = "completed";

        logger.info(
            "Sub-conversation merged",
            sub_conversation_id=sub_conversation_id,
            main_conversation_id=delegation["main_conversation_id"]
        );

        return True

    async def get_active_delegations(
        self,
        main_conversation_id: Optional[str] = None
    ) -> List[dict]:
        """
        Get active delegations

        Args:
            main_conversation_id: Optional filter by main conversation

        Returns:
            List of active delegations
        """
        delegations = [];
        for sub_id, delegation in self._delegations.items():
            if (
                delegation["status"] == "active"
                and (main_conversation_id is None
                     or delegation["main_conversation_id"] == main_conversation_id)
            ):
                delegations.append({
                    "sub_conversation_id": sub_id,
                    **delegation
                });

        return delegations

