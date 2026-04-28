"""
Floor Manager - Main OFP 1.1.0 Floor Control Component

Per OFP 1.1.0 Specification:
- Floor Manager includes envelope routing (not a separate component)
- If convener present: Floor Manager delegates floor decisions to Convener
- If no convener: Floor Manager has minimal behavior (first-come-first-served)

The Floor Manager is responsible for:
1. Receiving and routing envelopes between agents
2. Processing floor control events (requestFloor, yieldFloor, etc.)
3. Delegating to Convener for floor decisions (if present)
4. Managing conversation state
"""

from typing import Optional, Dict, Callable, List
import asyncio
import structlog
from datetime import datetime

from src.config import settings
from src.floor_manager.envelope import (
    OpenFloorEnvelope,
    EventType,
    EventObject,
    SchemaObject,
    ConversationObject,
    SenderObject,
    ToObject
)
from src.floor_manager.floor_control import FloorControl

logger = structlog.get_logger()


class FloorManager:
    """
    Floor Manager per OFP 1.1.0
    
    Central component that:
    - Routes envelopes between agents (built-in, not separate component)
    - Processes floor control events
    - Delegates to Convener for floor decisions
    - Implements minimal behavior if no convener present
    """
    
    def __init__(self, convener: Optional[FloorControl] = None) -> None:
        """
        Initialize Floor Manager
        
        Args:
            convener: Optional Convener component for floor decisions
                     If None, uses minimal first-come-first-served behavior
        """
        # Convener handles floor decisions (or None for minimal behavior)
        self.convener = convener or FloorControl()
        
        # Envelope routing (built into Floor Manager per OFP 1.0.1)
        self._routes: Dict[str, Callable] = {}
        self._queue: asyncio.Queue = asyncio.Queue(
            maxsize=settings.ROUTER_QUEUE_SIZE
        )
        self._max_retries = settings.ROUTER_MAX_RETRIES
        self._timeout = settings.ROUTER_TIMEOUT
        self._running = False
        
        logger.info(
            "Floor Manager initialized",
            has_convener=convener is not None
        )
    
    # =========================================================================
    # ENVELOPE ROUTING (Built into Floor Manager per OFP 1.0.1)
    # =========================================================================
    
    async def register_route(
        self,
        speakerUri: str,
        handler: Callable[[OpenFloorEnvelope], None]
    ) -> None:
        """
        Register routing handler for an agent
        
        Note: This is for envelope delivery, NOT agent registration.
        Per OFP 1.1.0, no agent registration exists.
        
        Args:
            speakerUri: Agent speaker URI (for envelope routing only)
            handler: Async handler function for envelopes
        """
        self._routes[speakerUri] = handler
        logger.info("Route registered for envelope delivery", speakerUri=speakerUri)
    
    async def unregister_route(self, speakerUri: str) -> None:
        """
        Unregister routing handler
        
        Args:
            speakerUri: Agent speaker URI
        """
        if speakerUri in self._routes:
            del self._routes[speakerUri]
            logger.info("Route unregistered", speakerUri=speakerUri)
    
    async def route_envelope(self, envelope: OpenFloorEnvelope) -> bool:
        """
        Route envelope to target agents based on events per OFP 1.1.0
        
        Per OFP 1.1.0:
        - Privacy flag ONLY respected for utterance events
        - All other events ignore privacy flag
        
        Args:
            envelope: Open Floor envelope to route
        
        Returns:
            True if routed successfully, False otherwise
        """
        routed = False
        
        for event in envelope.events:
            # OFP 1.1.0: Privacy flag only respected for utterance events
            is_private = (
                event.to is not None
                and event.to.private
                and event.eventType == EventType.UTTERANCE
            )
            
            # If no 'to' section, event is for all recipients
            if event.to is None:
                # Broadcast to all registered agents except sender
                for speakerUri, handler in self._routes.items():
                    if speakerUri == envelope.sender.speakerUri:
                        continue
                    try:
                        await asyncio.wait_for(
                            handler(envelope),
                            timeout=self._timeout
                        )
                        routed = True
                    except Exception as e:
                        logger.error(
                            "Routing error",
                            speakerUri=speakerUri,
                            error=str(e)
                        )
                continue
            
            # Route to specific agent
            target_speakerUri = event.to.speakerUri
            if not target_speakerUri:
                logger.warning("Event has 'to' section but no speakerUri")
                continue
            
            # For private utterance events, only route to intended recipient
            if is_private:
                if target_speakerUri not in self._routes:
                    logger.warning(
                        "No route found for private event recipient",
                        speakerUri=target_speakerUri
                    )
                    continue
                
                try:
                    await asyncio.wait_for(
                        self._routes[target_speakerUri](envelope),
                        timeout=self._timeout
                    )
                    routed = True
                    logger.debug(
                        "Private utterance routed",
                        speakerUri=target_speakerUri
                    )
                except Exception as e:
                    logger.error(
                        "Private routing error",
                        speakerUri=target_speakerUri,
                        error=str(e)
                    )
                continue
            
            # For non-utterance events or non-private utterances:
            # Privacy flag is ignored per OFP 1.1.0
            # Route to intended recipient
            if target_speakerUri not in self._routes:
                logger.warning(
                    "No route found for agent",
                    speakerUri=target_speakerUri
                )
                continue
            
            try:
                await asyncio.wait_for(
                    self._routes[target_speakerUri](envelope),
                    timeout=self._timeout
                )
                routed = True
                logger.debug(
                    "Envelope routed",
                    speakerUri=target_speakerUri,
                    eventType=event.eventType
                )
            except asyncio.TimeoutError:
                logger.error(
                    "Routing timeout",
                    speakerUri=target_speakerUri
                )
            except Exception as e:
                logger.error(
                    "Routing error",
                    speakerUri=target_speakerUri,
                    error=str(e)
                )
        
        return routed
    
    # =========================================================================
    # ENVELOPE PROCESSING (Floor Control Events)
    # =========================================================================
    
    async def process_envelope(self, envelope: OpenFloorEnvelope) -> bool:
        """
        Process incoming envelope and handle floor control events
        
        This is the main entry point for all envelopes.
        Floor Manager processes events and delegates to Convener as needed.
        
        Args:
            envelope: Open Floor envelope to process
        
        Returns:
            True if processed successfully
        """
        logger.info(
            "Processing envelope",
            conversation_id=envelope.conversation.id,
            sender=envelope.sender.speakerUri,
            num_events=len(envelope.events)
        )
        
        for event in envelope.events:
            await self._process_event(envelope, event)
        
        # Route envelope to other agents
        await self.route_envelope(envelope)
        
        return True
    
    async def _process_event(
        self,
        envelope: OpenFloorEnvelope,
        event: EventObject
    ) -> None:
        """
        Process individual event
        
        Per OFP 1.1.0: Floor Manager delegates floor decisions to Convener
        """
        conversation_id = envelope.conversation.id
        sender_uri = envelope.sender.speakerUri
        
        if event.eventType == EventType.REQUEST_FLOOR:
            # Delegate to Convener (if present)
            if self.convener:
                priority = event.parameters.get("priority", 0) if event.parameters else 0
                await self.convener.request_floor(
                    conversation_id,
                    sender_uri,
                    priority
                )
            else:
                # Minimal behavior: first-come-first-served
                await self._minimal_floor_grant(conversation_id, sender_uri)
        
        elif event.eventType == EventType.YIELD_FLOOR:
            # Delegate to Convener (if present)
            if self.convener:
                await self.convener.release_floor(conversation_id, sender_uri)
            else:
                # Minimal behavior: just release
                logger.info("Floor released (minimal mode)", speakerUri=sender_uri)
        
        elif event.eventType == EventType.UTTERANCE:
            # Just log utterance
            logger.debug(
                "Utterance received",
                conversation_id=conversation_id,
                speaker=sender_uri
            )
        
        # Other events are pass-through (routed but not specially processed)
    
    async def _minimal_floor_grant(self, conversation_id: str, speakerUri: str) -> None:
        """
        Minimal floor grant behavior (when no convener present)
        
        Simple first-come-first-served: grant floor to anyone who requests
        """
        logger.info(
            "Floor granted (minimal mode)",
            conversation_id=conversation_id,
            speakerUri=speakerUri
        )
    
    # =========================================================================
    # CONVENIENCE METHODS (Envelope Creation)
    # =========================================================================
    
    async def create_envelope(
        self,
        conversation_id: str,
        sender_speakerUri: str,
        sender_serviceUrl: Optional[str] = None,
        events: Optional[List[EventObject]] = None
    ) -> OpenFloorEnvelope:
        """
        Create a new Open Floor envelope
        
        Args:
            conversation_id: Conversation identifier
            sender_speakerUri: Sender speaker URI
            sender_serviceUrl: Optional sender service URL
            events: List of events (defaults to empty list)
        
        Returns:
            Created envelope
        """
        schema = SchemaObject(version="1.1.0")
        conversation = ConversationObject(id=conversation_id)
        sender = SenderObject(
            speakerUri=sender_speakerUri,
            serviceUrl=sender_serviceUrl
        )
        
        return OpenFloorEnvelope(
            schema_obj=schema,
            conversation=conversation,
            sender=sender,
            events=events or []
        )
    
    async def send_utterance(
        self,
        conversation_id: str,
        sender_speakerUri: str,
        sender_serviceUrl: Optional[str],
        target_speakerUri: Optional[str],
        target_serviceUrl: Optional[str],
        text: str,
        private: bool = False
    ) -> OpenFloorEnvelope:
        """
        Send an utterance event
        
        Args:
            conversation_id: Conversation identifier
            sender_speakerUri: Sender speaker URI
            sender_serviceUrl: Optional sender service URL
            target_speakerUri: Optional target speaker URI
            target_serviceUrl: Optional target service URL
            text: Utterance text
            private: Whether utterance is private (only respected for utterance per OFP 1.1.0)
        
        Returns:
            Created envelope
        """
        to_obj = None
        if target_speakerUri:
            to_obj = ToObject(
                speakerUri=target_speakerUri,
                serviceUrl=target_serviceUrl,
                private=private
            )
        
        event = EventObject(
            to=to_obj,
            eventType=EventType.UTTERANCE,
            parameters={
                "dialogEvent": {
                    "speakerUri": sender_speakerUri,
                    "features": {
                        "text": {
                            "mimeType": "text/plain",
                            "tokens": [{"token": text}]
                        }
                    }
                }
            }
        )
        
        envelope = await self.create_envelope(
            conversation_id=conversation_id,
            sender_speakerUri=sender_speakerUri,
            sender_serviceUrl=sender_serviceUrl,
            events=[event]
        )
        
        await self.route_envelope(envelope)
        return envelope
    
    # =========================================================================
    # LIFECYCLE
    # =========================================================================
    
    async def start(self) -> None:
        """Start Floor Manager"""
        self._running = True
        logger.info("Floor Manager started")
    
    async def stop(self) -> None:
        """Stop Floor Manager"""
        self._running = False
        logger.info("Floor Manager stopped")

