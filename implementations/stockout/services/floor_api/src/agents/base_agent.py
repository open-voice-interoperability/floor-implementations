"""
Base Agent - Base class for OFP 1.0.1 agents
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import structlog

from src.floor_manager.envelope import OpenFloorEnvelope, EventType, EventObject

logger = structlog.get_logger()


class BaseAgent(ABC):
    """
    Base class for Open Floor Protocol 1.0.1 agents
    
    Per OFP 1.0.1:
    - Agents identified only by speakerUri
    - NO agent registry or capabilities registry
    - Agents communicate via Floor Manager
    """

    def __init__(
        self,
        speakerUri: str,
        agent_name: str,
        serviceUrl: Optional[str] = None,
        agent_version: str = "1.1.0"
    ) -> None:
        """
        Initialize base agent

        Args:
            speakerUri: Unique URI identifying the agent (per OFP 1.0.1)
            agent_name: Human-readable agent name
            serviceUrl: Optional service URL
            agent_version: Agent version
        """
        self.speakerUri = speakerUri
        self.serviceUrl = serviceUrl
        self.agent_name = agent_name
        self.agent_version = agent_version

    @abstractmethod
    async def handle_envelope(
        self,
        envelope: OpenFloorEnvelope
    ) -> Optional[OpenFloorEnvelope]:
        """
        Handle incoming conversation envelope

        Args:
            envelope: Open Floor envelope to handle

        Returns:
            Response envelope or None
        """
        pass

    @abstractmethod
    async def process_utterance(
        self,
        conversation_id: str,
        utterance_text: str,
        sender_speakerUri: str
    ) -> Optional[str]:
        """
        Process an utterance

        Args:
            conversation_id: Conversation identifier
            utterance_text: Text of the utterance
            sender_speakerUri: Speaker URI of the sender

        Returns:
            Response text or None
        """
        pass

    async def start(self) -> None:
        """Start agent"""
        logger.info("Agent started", speakerUri=self.speakerUri)

    async def stop(self) -> None:
        """Stop agent"""
        logger.info("Agent stopped", speakerUri=self.speakerUri)
