"""
Conversation Envelope - OFP 1.1.0 Interoperable Conversation Envelope Specification
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict


class EventType(str, Enum):
    """Event type enumeration per OFP 1.1.0"""
    # Speaking or sending multi-media events
    UTTERANCE = "utterance"
    CONTEXT = "context"
    
    # Joining or leaving conversations
    INVITE = "invite"
    UNINVITE = "uninvite"
    ACCEPT_INVITE = "acceptInvite"  # Added in OFP 1.0.1
    DECLINE_INVITE = "declineInvite"
    BYE = "bye"
    
    # Discovering other agents
    GET_MANIFESTS = "getManifests"
    PUBLISH_MANIFESTS = "publishManifests"
    
    # Floor management
    REQUEST_FLOOR = "requestFloor"
    GRANT_FLOOR = "grantFloor"
    REVOKE_FLOOR = "revokeFloor"
    YIELD_FLOOR = "yieldFloor"


class SchemaObject(BaseModel):
    """Schema object per OFP 1.1.0"""
    version: str = Field("1.1.0", description="Schema version")
    url: Optional[str] = Field(
        None,
        description="URL to JSON schema for validation"
    )
    
    model_config = ConfigDict(
        # Avoid shadowing BaseModel.schema
        json_schema_extra={"examples": [{"version": "1.1.0"}]}
    )


class ConversantIdentification(BaseModel):
    """Conversant identification per OFP 1.1.0"""
    speakerUri: str = Field(..., description="Unique URI identifying the agent")
    serviceUrl: Optional[str] = Field(None, description="URL of the agent service")
    organization: Optional[str] = None
    conversationalName: Optional[str] = None
    department: Optional[str] = None
    role: Optional[str] = None
    synopsis: Optional[str] = None


class ConversantObject(BaseModel):
    """Conversant object per OFP 1.1.0
    
    Note: persistentState was removed in OFP 1.0.1 due to state management issues
    in multi-party conversations. Agents should use their own session management
    based on conversation ID.
    """
    identification: ConversantIdentification = Field(..., description="Agent identification")
    # persistentState removed in OFP 1.0.1, not present in 1.1.0


class ConversationObject(BaseModel):
    """Conversation object per OFP 1.1.0"""
    id: str = Field(..., description="Unique conversation identifier")
    conversants: Optional[List[ConversantObject]] = Field(
        None,
        description="List of conversants in the conversation"
    )
    assignedFloorRoles: Optional[Dict[str, List[str]]] = Field(
        None,
        description="Assigned floor roles mapping role names to arrays of speakerURIs (e.g., {'convener': ['tag:example.com,2025:floor_manager']})"
    )
    floorGranted: Optional[List[str]] = Field(
        None,
        description="Array of speakerURIs for conversants who currently have floor rights"
    )


class SenderObject(BaseModel):
    """Sender object per OFP 1.1.0"""
    speakerUri: str = Field(..., description="Unique URI identifying the sender")
    serviceUrl: Optional[str] = Field(
        None,
        description="URL of the sender service"
    )


class ToObject(BaseModel):
    """To object for event addressing per OFP 1.1.0
    
    Note: The 'private' flag is only respected for utterance events.
    For all other events, the privacy flag is ignored per OFP 1.1.0.
    """
    speakerUri: Optional[str] = Field(None, description="URI of intended recipient")
    serviceUrl: Optional[str] = Field(None, description="URL of intended recipient")
    private: bool = Field(False, description="Whether event is private (only for utterance events)")


class EventObject(BaseModel):
    """Event object per OFP 1.1.0"""
    to: Optional[ToObject] = Field(
        None,
        description="Target recipient (optional, if absent event is for all)"
    )
    eventType: EventType = Field(..., description="Type of event")
    reason: Optional[str] = Field(
        None,
        description="Reason for sending event (may contain @tokens like @timeout, @override)"
    )
    parameters: Optional[Dict[str, Any]] = Field(
        None,
        description="Event-specific parameters"
    )


class OpenFloorEnvelope(BaseModel):
    """
    Open Floor Conversation Envelope per OFP 1.1.0 specification
    
    Structure:
    {
      "openFloor": {
        "schema": {...},
        "conversation": {...},
        "sender": {...},
        "events": [...]
      }
    }
    
    Key features in OFP 1.1.0:
    - Floor is an autonomous state machine with optional convener
    - assignedFloorRoles: Dictionary mapping roles to arrays of speakerURIs
    - floorGranted: Array of speakerURIs with floor rights (simplified from 1.0.1)
    - acceptInvite event support
    - persistentState removed from conversants (since 1.0.1)
    - Privacy flag only respected for utterance events
    """

    schema_obj: SchemaObject = Field(
        ...,
        alias="schema",  # JSON field is "schema", Python attribute avoids shadowing BaseModel.schema
        description="Schema version and URL"
    )
    conversation: ConversationObject = Field(..., description="Conversation information")
    sender: SenderObject = Field(..., description="Sender information")
    events: List[EventObject] = Field(..., description="List of events")

    model_config = ConfigDict(
        populate_by_name=True,  # Allow both alias "schema" and attribute name "schema_obj"
        json_encoders={
            datetime: lambda v: v.isoformat()
        }
    )

    def to_dict(self) -> dict:
        """Convert envelope to dictionary with openFloor wrapper"""
        return {"openFloor": self.model_dump(exclude_none=True)}

    @classmethod
    def from_dict(cls, data: dict) -> "OpenFloorEnvelope":
        """Create envelope from dictionary"""
        if "openFloor" in data:
            return cls(**data["openFloor"]);
        return cls(**data)

    def get_events_for_agent(
        self,
        speakerUri: str,
        serviceUrl: Optional[str] = None
    ) -> List[EventObject]:
        """
        Get events intended for a specific agent
        
        Args:
            speakerUri: Agent speaker URI
            serviceUrl: Optional service URL for matching
            
        Returns:
            List of events for this agent
        """
        events = [];
        for event in self.events:
            # If no 'to' section, event is for all recipients
            if event.to is None:
                events.append(event);
                continue

            # Check if event is addressed to this agent
            if (
                event.to.speakerUri == speakerUri
                or (serviceUrl and event.to.serviceUrl == serviceUrl)
            ):
                events.append(event);

        return events


# Alias for backward compatibility
ConversationEnvelope = OpenFloorEnvelope
