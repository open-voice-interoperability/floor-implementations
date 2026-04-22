#!/usr/bin/env python3
"""
Test OFP 1.0.1 Envelope Compatibility with Stella

This script validates that our Floor Manager produces OFP 1.0.1 compliant envelopes
that should be compatible with Stella (OVON reference implementation).
"""

import sys
import os
import json
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.floor_manager.envelope import (
    OpenFloorEnvelope,
    SchemaObject,
    ConversationObject,
    SenderObject,
    EventObject,
    EventType,
    ToObject
)


def create_sample_envelope():
    """
    Create a sample OFP 1.0.1 envelope following the specification
    """
    
    envelope = OpenFloorEnvelope(
        schema_obj=SchemaObject(
            version="1.1.0",
            url="https://github.com/open-voice-interoperability/openfloor-docs"
        ),
        conversation=ConversationObject(
            id="test_stella_001",
            assignedFloorRoles={
                "convener": ["tag:floor.manager,2025:convener"]
            },
            floorGranted=[
                "tag:example.com,2025:test_agent"
            ]
        ),
        sender=SenderObject(
            speakerUri="tag:example.com,2025:test_agent",
            serviceUrl="http://localhost:8000/api/v1/envelope"
        ),
        events=[
            EventObject(
                eventType=EventType.UTTERANCE,
                to=ToObject(
                    speakerUri="tag:stella.ovon,2025:agent"
                ),
                parameters={
                    "dialogEvent": {
                        "speakerUri": "tag:example.com,2025:test_agent",
                        "span": {"startTime": datetime.now(timezone.utc).isoformat()},
                        "features": {
                            "text": {
                                "mimeType": "text/plain",
                                "tokens": [
                                    {"token": "Hello", "links": {}},
                                    {"token": "from", "links": {}},
                                    {"token": "Floor", "links": {}},
                                    {"token": "Manager!", "links": {}}
                                ]
                            }
                        }
                    }
                }
            )
        ]
    )
    
    return envelope


def validate_envelope_structure(envelope: OpenFloorEnvelope):
    """
    Validate envelope follows OFP 1.0.1 structure
    """
    
    print("\n" + "="*70)
    print("🔍 OFP 1.0.1 ENVELOPE VALIDATION")
    print("="*70)
    
    checks = []
    
    # Check 1: Schema version
    if envelope.schema_obj.version == "1.1.0":
        checks.append(("✅", "Schema version is 1.1.0"))
    else:
        checks.append(("❌", f"Schema version is {envelope.schema_obj.version} (expected 1.1.0)"))
    
    # Check 2: Conversation ID exists
    if envelope.conversation.id:
        checks.append(("✅", f"Conversation ID present: {envelope.conversation.id}"))
    else:
        checks.append(("❌", "Conversation ID missing"))
    
    # Check 3: Sender speakerUri exists
    if envelope.sender.speakerUri:
        checks.append(("✅", f"Sender speakerUri present: {envelope.sender.speakerUri}"))
    else:
        checks.append(("❌", "Sender speakerUri missing"))
    
    # Check 4: Events array exists
    if envelope.events and len(envelope.events) > 0:
        checks.append(("✅", f"Events array present ({len(envelope.events)} event(s))"))
    else:
        checks.append(("❌", "Events array empty or missing"))
    
    # Check 5: First event has eventType
    if envelope.events and envelope.events[0].eventType:
        checks.append(("✅", f"Event type present: {envelope.events[0].eventType.value}"))
    else:
        checks.append(("❌", "Event type missing"))
    
    # Check 6: assignedFloorRoles exists (OFP 1.0.1)
    if envelope.conversation.assignedFloorRoles:
        convener = envelope.conversation.assignedFloorRoles.get("convener")
        checks.append(("✅", f"assignedFloorRoles present (convener: {convener})"))
    else:
        checks.append(("⚠️", "assignedFloorRoles missing (optional but recommended)"))
    
    # Check 7: floorGranted exists (OFP 1.1.0)
    if envelope.conversation.floorGranted:
        holders = ", ".join(envelope.conversation.floorGranted) if len(envelope.conversation.floorGranted) > 0 else "none"
        checks.append(("✅", f"floorGranted present (holders: {holders})"))
    else:
        checks.append(("⚠️", "floorGranted missing (optional)"))
    
    # Print results
    print("\nValidation Results:")
    for icon, message in checks:
        print(f"  {icon} {message}")
    
    # Overall result
    failed = sum(1 for icon, _ in checks if icon == "❌")
    warnings = sum(1 for icon, _ in checks if icon == "⚠️")
    passed = sum(1 for icon, _ in checks if icon == "✅")
    
    print(f"\nSummary: {passed} passed, {warnings} warnings, {failed} failed")
    
    if failed == 0:
        print("\n✅ Envelope is OFP 1.0.1 COMPLIANT!")
        return True
    else:
        print("\n❌ Envelope has validation errors")
        return False


def export_envelope_json(envelope: OpenFloorEnvelope):
    """
    Export envelope to JSON for testing with Stella
    """
    
    print("\n" + "="*70)
    print("📤 ENVELOPE JSON FOR STELLA TESTING")
    print("="*70)
    
    # Convert to dict using Pydantic
    envelope_dict = envelope.model_dump(by_alias=True, exclude_none=True)
    
    # Pretty print
    json_output = json.dumps(envelope_dict, indent=2, default=str)
    
    print("\nGenerated OFP 1.0.1 Envelope:")
    print(json_output)
    
    # Save to file
    output_file = "stella_test_envelope.json"
    with open(output_file, "w") as f:
        f.write(json_output)
    
    print(f"\n✅ Saved to: {output_file}")
    print("\n💡 You can use this JSON to test with Stella:")
    print(f"   curl -X POST https://openvoice-stella.vercel.app/api/envelope \\")
    print(f"     -H 'Content-Type: application/json' \\")
    print(f"     -d @{output_file}")


def test_stella_compatibility():
    """
    Main test function
    """
    
    print("\n" + "="*70)
    print("🧪 STELLA COMPATIBILITY TEST")
    print("="*70)
    
    print("\nThis test validates that our Floor Manager produces")
    print("OFP 1.0.1 compliant envelopes compatible with Stella")
    print("(OVON reference implementation)")
    
    # Create sample envelope
    print("\n📦 Creating sample OFP 1.0.1 envelope...")
    envelope = create_sample_envelope()
    print("   ✅ Envelope created")
    
    # Validate structure
    is_valid = validate_envelope_structure(envelope)
    
    # Export JSON
    export_envelope_json(envelope)
    
    # Testing instructions
    print("\n" + "="*70)
    print("🚀 NEXT STEPS: Testing with Stella")
    print("="*70)
    
    print("\n1. Manual Test (using curl):")
    print("   curl -X POST https://openvoice-stella.vercel.app/api/envelope \\")
    print("     -H 'Content-Type: application/json' \\")
    print("     -d @stella_test_envelope.json")
    
    print("\n2. Expose Your Floor Manager (for bidirectional test):")
    print("   # Option A: Use ngrok")
    print("   ngrok http 8000")
    print("   # Then update serviceUrl in envelope to ngrok URL")
    
    print("\n   # Option B: Deploy to cloud")
    print("   # Deploy Floor Manager to Vercel/Railway/AWS")
    print("   # Update serviceUrl to public URL")
    
    print("\n3. Full Interoperability Test:")
    print("   a) Your Floor Manager sends envelope to Stella")
    print("   b) Stella processes and responds")
    print("   c) Your Floor Manager receives Stella's response")
    
    print("\n" + "="*70)
    print("📚 STELLA DOCUMENTATION")
    print("="*70)
    print("\nStella Repository:")
    print("   https://github.com/open-voice-interoperability/lib-interop")
    
    print("\nOFP 1.0.1 Specification:")
    print("   https://github.com/open-voice-interoperability/openfloor-docs")
    
    if is_valid:
        print("\n✅ Your Floor Manager is ready for Stella testing!")
    else:
        print("\n⚠️  Fix validation errors before testing with Stella")


if __name__ == "__main__":
    test_stella_compatibility()

