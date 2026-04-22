#!/usr/bin/env python3
"""
Stella Integration Test - Full bidirectional OFP 1.0.1 test

This script tests real interoperability between your Floor Manager and Stella.

Requirements:
1. Floor Manager running (docker-compose up)
2. Public URL for your Floor Manager (via ngrok or deployment)
"""

import asyncio
import httpx
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

# Stella endpoint
STELLA_URL = "https://openvoice-stella.vercel.app/api/envelope"

# Your Floor Manager endpoint (change this to your ngrok URL)
YOUR_FLOOR_MANAGER_URL = "http://localhost:8000/api/v1/envelope"


async def test_send_to_stella(
    your_public_url: str,
    test_message: str = "Hello Stella! Testing OFP 1.0.1 interoperability."
):
    """
    Test 1: Send envelope from your Floor Manager to Stella
    """
    
    print("\n" + "="*70)
    print("🧪 TEST 1: Send Envelope to Stella")
    print("="*70)
    
    # Create envelope
    envelope = OpenFloorEnvelope(
        schema_obj=SchemaObject(
            version="1.1.0",
            url="https://github.com/open-voice-interoperability/openfloor-docs"
        ),
        conversation=ConversationObject(
            id=f"floor_to_stella_{int(datetime.now(timezone.utc).timestamp())}",
            assignedFloorRoles={
                "convener": ["tag:floor.manager,2025:convener"]
            },
            floorGranted=[
                "tag:floor.manager,2025:test_agent"
            ]
        ),
        sender=SenderObject(
            speakerUri="tag:floor.manager,2025:test_agent",
            serviceUrl=your_public_url  # Where Stella should respond
        ),
        events=[
            EventObject(
                eventType=EventType.UTTERANCE,
                to=ToObject(speakerUri="tag:stella.ovon,2025:agent"),
                parameters={
                    "dialogEvent": {
                        "speakerUri": "tag:floor.manager,2025:test_agent",
                        "span": {"startTime": datetime.now(timezone.utc).isoformat()},
                        "features": {
                            "text": {
                                "mimeType": "text/plain",
                                "tokens": [{"token": word, "links": {}} for word in test_message.split()]
                            }
                        }
                    }
                }
            )
        ]
    )
    
    print(f"\n📤 Sending to Stella: {STELLA_URL}")
    print(f"📩 Message: {test_message}")
    print(f"🔗 Your serviceUrl: {your_public_url}")
    
    # Convert to JSON
    envelope_dict = envelope.model_dump(by_alias=True, exclude_none=True)
    
    # Send to Stella
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                STELLA_URL,
                json=envelope_dict,
                headers={"Content-Type": "application/json"}
            )
            
            print(f"\n📨 Response Status: {response.status_code}")
            print(f"📨 Response Body: {response.text[:500]}")
            
            if response.status_code == 200:
                print("\n✅ SUCCESS! Stella accepted your envelope!")
                print("   Your Floor Manager is OFP 1.0.1 compatible!")
                return True
            elif response.status_code == 404:
                print("\n⚠️  404 Not Found - Stella endpoint might have changed")
                print("   Check: https://github.com/open-voice-interoperability/lib-interop")
            else:
                print(f"\n❌ Failed with status {response.status_code}")
                try:
                    error_detail = response.json()
                    print(f"   Error: {json.dumps(error_detail, indent=2)}")
                except:
                    print(f"   Response: {response.text}")
            
            return False
            
        except httpx.ConnectError:
            print(f"\n❌ Cannot connect to Stella at {STELLA_URL}")
            print("   Stella might be down or URL changed")
            return False
        except Exception as e:
            print(f"\n❌ Error: {e}")
            return False


async def test_receive_from_stella():
    """
    Test 2: Check if your Floor Manager can receive envelopes from Stella
    
    This requires:
    1. Your Floor Manager has a public URL (ngrok or deployed)
    2. Stella sends response to your serviceUrl
    """
    
    print("\n" + "="*70)
    print("🧪 TEST 2: Receive Response from Stella")
    print("="*70)
    
    print("\n⚠️  This test requires:")
    print("   1. Your Floor Manager exposed via public URL")
    print("   2. Stella configured to send response to your serviceUrl")
    print("\n💡 To set up:")
    print("   # Terminal 1: Start Floor Manager")
    print("   docker-compose up")
    print("\n   # Terminal 2: Expose with ngrok")
    print("   ngrok http 8000")
    print("\n   # Update YOUR_FLOOR_MANAGER_URL in this script to ngrok URL")
    
    return False


async def test_floor_control_with_stella(your_public_url: str):
    """
    Test 3: Test floor control events with Stella
    """
    
    print("\n" + "="*70)
    print("🧪 TEST 3: Floor Control Events with Stella")
    print("="*70)
    
    conversation_id = f"floor_control_test_{int(datetime.now(timezone.utc).timestamp())}"
    
    # Test requestFloor event
    print("\n📤 Sending requestFloor event to Stella...")
    
    envelope = OpenFloorEnvelope(
            schema_obj=SchemaObject(version="1.1.0"),
        conversation=ConversationObject(
            id=conversation_id,
            assignedFloorRoles={
                "convener": "tag:stella.ovon,2025:agent"  # Stella is convener
            }
        ),
        sender=SenderObject(
            speakerUri="tag:floor.manager,2025:test_agent",
            serviceUrl=your_public_url
        ),
        events=[
            EventObject(
                eventType=EventType.REQUEST_FLOOR,
                to=ToObject(speakerUri="tag:stella.ovon,2025:agent"),
                parameters={
                    "priority": 5,
                    "reason": "Testing OFP 1.0.1 floor control"
                }
            )
        ]
    )
    
    envelope_dict = envelope.model_dump(by_alias=True, exclude_none=True)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                STELLA_URL,
                json=envelope_dict,
                headers={"Content-Type": "application/json"}
            )
            
            print(f"\n📨 Response Status: {response.status_code}")
            
            if response.status_code == 200:
                print("✅ requestFloor event accepted by Stella!")
                print("   Floor control interoperability working!")
                return True
            else:
                print(f"❌ Failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return False


async def main():
    """
    Run all Stella integration tests
    """
    
    print("\n" + "="*70)
    print("🚀 STELLA INTEGRATION TEST SUITE")
    print("="*70)
    
    print("\nThis test suite validates OFP 1.0.1 interoperability between")
    print("your Floor Manager and Stella (OVON reference implementation)")
    
    # Check if user configured public URL
    your_public_url = os.getenv("FLOOR_MANAGER_PUBLIC_URL", YOUR_FLOOR_MANAGER_URL)
    
    if "localhost" in your_public_url:
        print("\n⚠️  WARNING: Using localhost URL")
        print("   Stella cannot reach localhost - bidirectional test will fail")
        print("\n💡 To enable full test:")
        print("   export FLOOR_MANAGER_PUBLIC_URL='https://your-ngrok-url.ngrok.io/api/v1/envelope'")
        print("   python examples/agents/test_stella_integration.py")
    else:
        print(f"\n✅ Using public URL: {your_public_url}")
    
    # Run tests
    results = []
    
    # Test 1: Send envelope to Stella
    result1 = await test_send_to_stella(your_public_url)
    results.append(("Send envelope to Stella", result1))
    
    await asyncio.sleep(2)
    
    # Test 2: Floor control with Stella
    if result1:  # Only if test 1 succeeded
        result3 = await test_floor_control_with_stella(your_public_url)
        results.append(("Floor control events", result3))
    
    # Test 3: Receive from Stella (informational)
    await test_receive_from_stella()
    
    # Summary
    print("\n" + "="*70)
    print("📊 TEST SUMMARY")
    print("="*70)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {status}: {test_name}")
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    print(f"\nResults: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("\n🎉 CONGRATULATIONS!")
        print("   Your Floor Manager is fully OFP 1.0.1 compatible with Stella!")
    elif passed_count > 0:
        print("\n✅ Partial Success!")
        print("   Your Floor Manager can communicate with Stella")
        print("   Set up ngrok for full bidirectional testing")
    else:
        print("\n❌ Tests Failed")
        print("   Check Stella availability and envelope format")
    
    # Next steps
    print("\n" + "="*70)
    print("📚 NEXT STEPS")
    print("="*70)
    
    print("\n1. Set up ngrok for bidirectional testing:")
    print("   ngrok http 8000")
    print("   export FLOOR_MANAGER_PUBLIC_URL='https://YOUR-URL.ngrok.io/api/v1/envelope'")
    
    print("\n2. Check Stella documentation:")
    print("   https://github.com/open-voice-interoperability/lib-interop")
    
    print("\n3. Review OFP 1.0.1 specification:")
    print("   https://github.com/open-voice-interoperability/openfloor-docs")


if __name__ == "__main__":
    asyncio.run(main())



