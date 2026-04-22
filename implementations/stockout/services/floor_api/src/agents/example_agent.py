"""
Example Agent - Example implementation of BaseAgent per OFP 1.0.1
"""

from typing import Optional
import structlog

from src.agents.base_agent import BaseAgent
from src.floor_manager.envelope import (
    OpenFloorEnvelope,
    EventType,
    EventObject,
    ToObject
)

logger = structlog.get_logger()


class ExampleAgent(BaseAgent):
    """
    Example agent implementation per OFP 1.0.1
    """

    def __init__(
        self,
        speakerUri: str = "tag:example.com,2025:example_agent",
        agent_name: str = "Example Agent",
        serviceUrl: Optional[str] = None,
        agent_version: str = "1.1.0"
    ) -> None:
        """Initialize example agent"""
        super().__init__(
            speakerUri=speakerUri,
            agent_name=agent_name,
            serviceUrl=serviceUrl,
            agent_version=agent_version
        )

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
        # Get events intended for this agent
        events_for_me = envelope.get_events_for_agent(
            self.speakerUri,
            self.serviceUrl
        );

        if not events_for_me:
            return None;

        logger.info(
            "Handling envelope",
            speakerUri=self.speakerUri,
            conversation_id=envelope.conversation.id,
            event_count=len(events_for_me)
        );

        response_events = [];

        for event in events_for_me:
            if event.eventType == EventType.UTTERANCE:
                # Extract utterance text from parameters
                utterance_text = "";
                if (
                    event.parameters
                    and "dialogEvent" in event.parameters
                    and "features" in event.parameters["dialogEvent"]
                    and "text" in event.parameters["dialogEvent"]["features"]
                    and "tokens" in event.parameters["dialogEvent"]["features"]["text"]
                ):
                    tokens = event.parameters["dialogEvent"]["features"]["text"]["tokens"];
                    utterance_text = " ".join(
                        token.get("token", "") for token in tokens
                    );

                # Process utterance
                response_text = await self.process_utterance(
                    envelope.conversation.id,
                    utterance_text,
                    envelope.sender.speakerUri
                );

                if response_text:
                    # Create response utterance event
                    response_event = EventObject(
                        to=ToObject(
                            speakerUri=envelope.sender.speakerUri,
                            serviceUrl=envelope.sender.serviceUrl
                        ),
                        eventType=EventType.UTTERANCE,
                        parameters={
                            "dialogEvent": {
                                "speakerUri": self.speakerUri,
                                "features": {
                                    "text": {
                                        "mimeType": "text/plain",
                                        "tokens": [{"token": response_text}]
                                    }
                                }
                            }
                        }
                    );
                    response_events.append(response_event);

        if not response_events:
            return None;

        # Create response envelope
        from src.floor_manager.envelope import (
            SchemaObject,
            ConversationObject,
            SenderObject
        )

        response_envelope = OpenFloorEnvelope(
            schema_obj=SchemaObject(version="1.1.0"),
            conversation=ConversationObject(id=envelope.conversation.id),
            sender=SenderObject(
                speakerUri=self.speakerUri,
                serviceUrl=self.serviceUrl
            ),
            events=response_events
        );

        return response_envelope

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
        logger.info(
            "Processing utterance",
            speakerUri=self.speakerUri,
            conversation_id=conversation_id,
            utterance_text=utterance_text[:50]  # Log first 50 chars
        );

        # Example processing logic - echo the utterance
        response = f"Echo: {utterance_text}";

        return response
