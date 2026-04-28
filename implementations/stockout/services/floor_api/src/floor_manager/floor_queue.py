"""
Floor Queue - Manages floor request queues
"""

from typing import List, Optional
from datetime import datetime
import structlog

from src.config import settings

logger = structlog.get_logger()


class FloorQueue:
    """
    Manages floor request queues per conversation
    """

    def __init__(self) -> None:
        """Initialize floor queue"""
        self._queues: dict[str, List[dict]] = {};
        self._max_size = settings.FLOOR_QUEUE_MAX_SIZE

    def enqueue(
        self,
        conversation_id: str,
        agent_id: str,
        priority: int = 0
    ) -> bool:
        """
        Add agent to floor request queue

        Args:
            conversation_id: Unique conversation identifier
            agent_id: Agent requesting floor
            priority: Request priority

        Returns:
            True if enqueued, False if queue full
        """
        if conversation_id not in self._queues:
            self._queues[conversation_id] = [];

        if len(self._queues[conversation_id]) >= self._max_size:
            logger.warning(
                "Floor queue full",
                conversation_id=conversation_id,
                max_size=self._max_size
            );
            return False

        request = {
            "agent_id": agent_id,
            "priority": priority,
            "timestamp": datetime.utcnow()
        };

        self._queues[conversation_id].append(request);
        self._queues[conversation_id].sort(
            key=lambda x: (-x["priority"], x["timestamp"])
        );

        logger.debug(
            "Agent enqueued",
            conversation_id=conversation_id,
            agent_id=agent_id,
            queue_position=len(self._queues[conversation_id])
        );

        return True

    def dequeue(self, conversation_id: str) -> Optional[dict]:
        """
        Remove and return next agent from queue

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            Next request dict or None if queue empty
        """
        if (
            conversation_id not in self._queues
            or not self._queues[conversation_id]
        ):
            return None

        return self._queues[conversation_id].pop(0);

    def peek(self, conversation_id: str) -> Optional[dict]:
        """
        Get next agent without removing from queue

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            Next request dict or None if queue empty
        """
        if (
            conversation_id not in self._queues
            or not self._queues[conversation_id]
        ):
            return None

        return self._queues[conversation_id][0];

    def get_queue_size(self, conversation_id: str) -> int:
        """
        Get queue size for conversation

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            Queue size
        """
        if conversation_id not in self._queues:
            return 0
        return len(self._queues[conversation_id]);

    def remove_agent(
        self,
        conversation_id: str,
        agent_id: str
    ) -> bool:
        """
        Remove agent from queue

        Args:
            conversation_id: Unique conversation identifier
            agent_id: Agent to remove

        Returns:
            True if removed, False if not found
        """
        if conversation_id not in self._queues:
            return False

        queue = self._queues[conversation_id];
        original_size = len(queue);

        self._queues[conversation_id] = [
            req for req in queue if req["agent_id"] != agent_id
        ];

        removed = len(self._queues[conversation_id]) < original_size;

        if removed:
            logger.debug(
                "Agent removed from queue",
                conversation_id=conversation_id,
                agent_id=agent_id
            );

        return removed;

