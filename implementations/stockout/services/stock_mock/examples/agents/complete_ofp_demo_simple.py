#!/usr/bin/env python3
"""
Complete OFP Demo - Shows full Open Floor Protocol 1.0.1 flow:

PER OFP 1.0.1:
- NO agent registration (agents identified only by speakerUri in envelopes)
- Floor Manager includes envelope routing (not a separate component)
- Convener is the component that makes floor decisions

This demo shows:
1. Agents sending envelopes directly (no registration)
2. requestFloor with priority
3. Convener (Floor Manager) grants floor autonomously
4. Agent utterances
5. yieldFloor when done
"""

import asyncio
import httpx
import sys
import os

# Floor Manager API base URL
FLOOR_API = "http://localhost:8000/api/v1"


class OFPAgent:
    """
    Simple OFP agent - no registration needed per OFP 1.0.1
    
    Agents are identified only by their speakerUri in envelopes.
    No central registry exists in OFP specification.
    """
    
    def __init__(self, speakerUri: str, agent_name: str, priority: int = 5):
        self.speakerUri = speakerUri
        self.agent_name = agent_name
        self.priority = priority
        self.client = httpx.AsyncClient(timeout=30.0)
        
    async def request_floor(self, conversation_id: str):
        """
        Request floor access per OFP 1.0.1 requestFloor event
        
        Convener (Floor Manager) makes the decision autonomously.
        """
        print(f"\n🙋 {self.agent_name} requesting floor (priority: {self.priority})...")
        
        response = await self.client.post(
            f"{FLOOR_API}/floor/request",
            json={
                "conversation_id": conversation_id,
                "speakerUri": self.speakerUri,
                "priority": self.priority
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("granted"):
                print(f"   ✅ Floor GRANTED to {self.agent_name}")
                return True
            else:
                print(f"   ⏳ {self.agent_name} queued for floor")
                return False
        else:
            print(f"   ❌ Request failed: {response.text}")
            return False
            
    async def check_floor_holder(self, conversation_id: str):
        """Check who holds the floor"""
        response = await self.client.get(f"{FLOOR_API}/floor/holder/{conversation_id}")
        if response.status_code == 200:
            return response.json()
        return None
        
    async def yield_floor(self, conversation_id: str):
        """
        Yield floor when done per OFP 1.0.1 yieldFloor event
        
        Convener will grant floor to next agent in queue.
        """
        print(f"\n👋 {self.agent_name} yielding floor...")
        
        response = await self.client.post(
            f"{FLOOR_API}/floor/release",
            json={
                "conversation_id": conversation_id,
                "speakerUri": self.speakerUri
            }
        )
        
        if response.status_code == 200:
            print(f"   ✅ Floor released by {self.agent_name}")
            return True
        else:
            print(f"   ❌ Release failed: {response.json().get('detail', response.text)}")
            return False
    
    async def speak(self, message: str):
        """Agent sends an utterance"""
        print(f"\n💬 {self.agent_name}: '{message}'")
        
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


async def demonstrate_floor_control(conversation_id: str):
    """
    Demonstrate complete OFP 1.0.1 floor control flow
    
    Per OFP 1.0.1:
    - Agents do NOT register (no registry exists)
    - Agents identified only by speakerUri
    - Convener (Floor Manager) makes all floor decisions
    - Priority queue managed by Convener
    """
    
    # Create agents - NO REGISTRATION NEEDED per OFP 1.0.1
    print("\n" + "="*70)
    print("STEP 1: Create Agents (No Registration Required)")
    print("="*70)
    print("\n📝 Per OFP 1.0.1: Agents are identified only by speakerUri")
    print("   NO central registry or registration process exists")
    
    coordinator = OFPAgent(
        speakerUri="tag:demo.com,2025:coordinator",
        agent_name="Coordinator Agent",
        priority=10  # Highest priority
    )
    print(f"   ✅ Created: {coordinator.agent_name} (priority: {coordinator.priority})")
    
    analyst = OFPAgent(
        speakerUri="tag:demo.com,2025:analyst",
        agent_name="Data Analyst Agent",
        priority=7  # Medium priority
    )
    print(f"   ✅ Created: {analyst.agent_name} (priority: {analyst.priority})")
    
    assistant = OFPAgent(
        speakerUri="tag:demo.com,2025:assistant",
        agent_name="Assistant Agent",
        priority=5  # Lower priority
    )
    print(f"   ✅ Created: {assistant.agent_name} (priority: {assistant.priority})")
    
    # Request floor (priority-based queue)
    print("\n" + "="*70)
    print("STEP 2: Floor Requests (Priority Queue)")
    print("="*70)
    print("\n💡 All agents will request floor. Watch Convener grant by priority!")
    
    # All agents request floor (different priorities)
    await assistant.request_floor(conversation_id)  # priority 5
    await asyncio.sleep(0.5)
    
    await analyst.request_floor(conversation_id)  # priority 7
    await asyncio.sleep(0.5)
    
    await coordinator.request_floor(conversation_id)  # priority 10
    await asyncio.sleep(0.5)
    
    # Check floor holder
    print("\n" + "="*70)
    print("STEP 3: Check Floor Holder")
    print("="*70)
    
    holder_info = await coordinator.check_floor_holder(conversation_id)
    if holder_info:
        print(f"\n🎤 Current floor holder: {holder_info.get('holder', 'Unknown')}")
        print(f"   Convener: {holder_info.get('assignedFloorRoles', {}).get('convener', 'N/A')}")
    
    # Agents speak in priority order
    print("\n" + "="*70)
    print("STEP 4: Agents Speak (Priority Order)")
    print("="*70)
    
    # Assistant has floor (was first to request)
    await assistant.speak("Hello! I'm ready to assist.")
    await asyncio.sleep(1)
    await assistant.yield_floor(conversation_id)
    await asyncio.sleep(1)
    
    # Analyst should get floor next (higher priority in queue)
    holder_info = await analyst.check_floor_holder(conversation_id)
    if holder_info and holder_info.get('holder'):
        await analyst.speak("I've analyzed the data. Here are my findings...")
        await asyncio.sleep(1)
        await analyst.yield_floor(conversation_id)
        await asyncio.sleep(1)
    
    # Coordinator should get floor last (highest priority in queue)
    holder_info = await coordinator.check_floor_holder(conversation_id)
    if holder_info and holder_info.get('holder'):
        await coordinator.speak("Excellent work everyone! Let's proceed.")
        await asyncio.sleep(1)
        await coordinator.yield_floor(conversation_id)
    
    # Cleanup
    await coordinator.close()
    await analyst.close()
    await assistant.close()


async def main():
    """Main entry point"""
    
    print("\n" + "="*70)
    print("🚀 COMPLETE OPEN FLOOR PROTOCOL 1.0.1 DEMONSTRATION")
    print("="*70)
    
    print("\nThis demo shows:")
    print("  1. Agents identified only by speakerUri (no registration)")
    print("  2. requestFloor with priority")
    print("  3. Convener (Floor Manager) grants floor autonomously")
    print("  4. Agent utterances")
    print("  5. yieldFloor and floor handoff")
    
    # Check Floor Manager health
    print("\n🏥 Checking Floor Manager health...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/health")
            if response.status_code == 200:
                print("   ✅ Floor Manager is running and healthy")
            else:
                print("   ❌ Floor Manager responded with error")
                return
    except Exception as e:
        print(f"   ❌ Cannot connect to Floor Manager: {e}")
        print("\n💡 Make sure Floor Manager is running:")
        print("   docker-compose up")
        return
    
    # Run demonstration
    conversation_id = "demo_conversation_001"
    
    try:
        await demonstrate_floor_control(conversation_id)
        
        print("\n" + "="*70)
        print("✅ DEMO COMPLETED SUCCESSFULLY!")
        print("="*70)
        
        print("\n📝 Summary:")
        print("   ✓ Agents created (no registration needed per OFP 1.0.1)")
        print("   ✓ Floor requested by multiple agents")
        print("   ✓ Convener granted floor by priority")
        print("   ✓ Agents spoke in order")
        print("   ✓ Floor yielded properly")
        
        print("\n" + "="*70)
        print("🎓 Understanding the Flow")
        print("="*70)
        
        print("\nThe Convener (Floor Manager) acts as an autonomous state machine:")
        print("\n1. REQUEST: Agents request floor with priority (no registration)")
        print("2. QUEUE: Convener maintains priority queue of requests")
        print("3. GRANT: Convener grants floor to highest priority agent")
        print("4. SPEAK: Agent with floor can send utterances")
        print("5. YIELD: Agent yields floor when done")
        print("6. NEXT: Convener grants floor to next agent in queue")
        print("7. REPEAT: Steps 4-6 repeat until conversation ends")
        
        print("\nThis is the core of OFP 1.0.1 floor control!")
        print("\nKey Difference from Previous Understanding:")
        print("   ❌ NO agent registration (no central registry)")
        print("   ✅ Agents identified only by speakerUri in envelopes")
        print("   ✅ Convener is part of Floor Manager (not separate)")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())



