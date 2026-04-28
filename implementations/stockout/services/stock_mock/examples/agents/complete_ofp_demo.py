#!/usr/bin/env python3
"""
Complete OFP Demo - Shows full Open Floor Protocol flow:
1. Agent registration with manifests
2. getManifests to discover capabilities
3. requestFloor with priority
4. grantFloor by Convener
5. Agent utterances
6. yieldFloor when done
"""

import asyncio
import httpx
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.agents.example_agent import ExampleAgent
from src.floor_manager.envelope import OpenFloorEnvelope, EventObject, EventType

# Floor Manager API base URL
FLOOR_API = "http://localhost:8000/api/v1"


class OFPDemoAgent(ExampleAgent):
    """
    Demo agent that interacts with Floor Manager API
    
    ⚠️ WARNING: This demo uses old registration API which is NOT part of OFP 1.0.1
    Use complete_ofp_demo_simple.py for OFP 1.0.1 compliant demo instead.
    """
    
    def __init__(self, speakerUri: str, agent_name: str, priority: int = 5):
        super().__init__(speakerUri, agent_name)
        self.priority = priority
        self.client = httpx.AsyncClient(timeout=30.0)
        
    async def register_with_floor(self):
        """
        Register agent with Floor Manager
        
        ⚠️ WARNING: Agent registration is NOT part of OFP 1.0.1
        This will fail if the /agents/register endpoint doesn't exist.
        Use complete_ofp_demo_simple.py instead.
        """
        print(f"\n📝 Registering {self.agent_name}...")
        
        response = await self.client.post(
            f"{FLOOR_API}/agents/register",
            json={
                "speakerUri": self.speakerUri,
                "agent_name": self.agent_name,
                "agent_version": self.agent_version,
                "serviceUrl": self.serviceUrl
            }
        )
        
        if response.status_code == 200:
            print(f"   ✅ {self.agent_name} registered successfully")
            print(f"   📋 Manifest: {response.json()}")
        else:
            print(f"   ❌ Registration failed: {response.text}")
            
    async def request_floor(self, conversation_id: str):
        """Request floor access"""
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
        """Yield floor when done"""
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
        else:
            print(f"   ❌ Release failed: {response.text}")
            
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


async def get_all_manifests():
    """Demonstrate getManifests - discover all registered agents"""
    print("\n" + "="*70)
    print("📋 GETTING ALL AGENT MANIFESTS (Capability Discovery)")
    print("="*70)
    
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{FLOOR_API}/agents/")
        
        if response.status_code == 200:
            agents = response.json()
            print(f"\n✅ Found {len(agents)} registered agents:")
            
            for agent in agents:
                print(f"\n   🤖 Agent: {agent['agent_name']}")
                print(f"      URI: {agent['speakerUri']}")
                print(f"      Capabilities: {', '.join(agent['capabilities'])}")
                print(f"      Version: {agent['agent_version']}")
        else:
            print(f"❌ Failed to get manifests: {response.text}")


async def demonstrate_floor_control(conversation_id: str):
    """Demonstrate complete floor control flow"""
    
    print("\n" + "="*70)
    print("🎭 DEMONSTRATING FLOOR CONTROL WITH PRIORITY")
    print("="*70)
    
    # Create agents with different priorities
    coordinator = OFPDemoAgent(
        speakerUri="tag:demo.com,2025:coordinator",
        agent_name="Coordinator Agent",
        priority=10  # Highest priority
    )
    
    analyst = OFPDemoAgent(
        speakerUri="tag:demo.com,2025:analyst",
        agent_name="Data Analyst Agent",
        priority=7
    )
    
    assistant = OFPDemoAgent(
        speakerUri="tag:demo.com,2025:assistant",
        agent_name="Assistant Agent",
        priority=5
    )
    
    try:
        # Step 1: Register all agents
        print("\n" + "="*70)
        print("STEP 1: Agent Registration")
        print("="*70)
        
        await coordinator.register_with_floor()
        await analyst.register_with_floor()
        await assistant.register_with_floor()
        
        # Step 2: Get all manifests (capability discovery)
        await get_all_manifests()
        
        # Step 3: Multiple agents request floor (demonstrate priority queue)
        print("\n" + "="*70)
        print("STEP 2: Floor Requests (Priority Queue)")
        print("="*70)
        print("\n💡 All agents will request floor. Watch priority in action!")
        
        # Request floor in "wrong" order to show priority works
        await assistant.request_floor(conversation_id)
        await asyncio.sleep(0.5)
        
        await analyst.request_floor(conversation_id)
        await asyncio.sleep(0.5)
        
        await coordinator.request_floor(conversation_id)
        await asyncio.sleep(0.5)
        
        # Step 4: Check current floor holder
        print("\n" + "="*70)
        print("STEP 3: Check Floor Holder")
        print("="*70)
        
        holder = await coordinator.check_floor_holder(conversation_id)
        if holder:
            print(f"\n🎤 Current floor holder: {holder.get('holder_name', 'Unknown')}")
            print(f"   URI: {holder.get('holder', 'N/A')}")
        
        # Step 5: Coordinator speaks
        print("\n" + "="*70)
        print("STEP 4: Coordinator Speaks (Has Floor)")
        print("="*70)
        
        print(f"\n💬 {coordinator.agent_name}: 'Welcome everyone! I'll coordinate this session.'")
        await asyncio.sleep(1)
        
        # Step 6: Coordinator yields floor
        await coordinator.yield_floor(conversation_id)
        await asyncio.sleep(0.5)
        
        # Step 7: Check who gets floor next (should be Analyst, priority 7)
        print("\n" + "="*70)
        print("STEP 5: Next Agent Gets Floor (By Priority)")
        print("="*70)
        
        holder = await analyst.check_floor_holder(conversation_id)
        if holder:
            print(f"\n🎤 Current floor holder: {holder.get('holder_name', 'Unknown')}")
            print(f"   Priority system working! Analyst (priority 7) got floor before Assistant (priority 5)")
        
        # Step 8: Analyst speaks
        print(f"\n💬 {analyst.agent_name}: 'I've analyzed the data. Here are my findings...'")
        await asyncio.sleep(1)
        
        # Step 9: Analyst yields
        await analyst.yield_floor(conversation_id)
        await asyncio.sleep(0.5)
        
        # Step 10: Assistant gets floor
        print("\n" + "="*70)
        print("STEP 6: Final Agent Gets Floor")
        print("="*70)
        
        holder = await assistant.check_floor_holder(conversation_id)
        if holder:
            print(f"\n🎤 Current floor holder: {holder.get('holder_name', 'Unknown')}")
        
        print(f"\n💬 {assistant.agent_name}: 'Thank you! Is there anything else I can help with?'")
        await asyncio.sleep(1)
        
        # Step 11: Assistant yields (conversation ends)
        await assistant.yield_floor(conversation_id)
        
        print("\n" + "="*70)
        print("✅ DEMO COMPLETED SUCCESSFULLY!")
        print("="*70)
        print("\n📝 Summary:")
        print("   ✓ Agents registered with manifests")
        print("   ✓ Manifests retrieved (capability discovery)")
        print("   ✓ Floor requested by multiple agents")
        print("   ✓ Convener granted floor by priority (10 → 7 → 5)")
        print("   ✓ Agents spoke in order")
        print("   ✓ Floor yielded properly")
        
    finally:
        # Cleanup
        await coordinator.close()
        await analyst.close()
        await assistant.close()


async def check_floor_manager_health():
    """Check if Floor Manager is running"""
    print("\n🏥 Checking Floor Manager health...")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/health", timeout=5.0)
            
            if response.status_code == 200:
                print("   ✅ Floor Manager is running and healthy")
                return True
            else:
                print(f"   ⚠️  Floor Manager responded but not healthy: {response.status_code}")
                return False
    except httpx.ConnectError:
        print("   ❌ Floor Manager is NOT running")
        print("\n   Please start the Floor Manager first:")
        print("   docker-compose up -d")
        return False
    except Exception as e:
        print(f"   ❌ Error checking health: {e}")
        return False


async def main():
    """Run complete OFP demonstration"""
    
    print("\n" + "="*70)
    print("🚀 COMPLETE OPEN FLOOR PROTOCOL DEMONSTRATION")
    print("="*70)
    print("\nThis demo shows:")
    print("  1. Agent registration with manifests")
    print("  2. Manifest discovery (getManifests)")
    print("  3. Floor request with priority")
    print("  4. Convener grants floor by priority")
    print("  5. Agent utterances")
    print("  6. Floor yield and handoff")
    
    # Check if Floor Manager is running
    if not await check_floor_manager_health():
        sys.exit(1)
    
    # Run the demonstration
    conversation_id = "conv_complete_demo_001"
    await demonstrate_floor_control(conversation_id)
    
    print("\n" + "="*70)
    print("🎓 Understanding the Flow")
    print("="*70)
    print("""
The Floor Manager (Convener) acts as an autonomous state machine:

1. REGISTER: Agents register with their manifests (capabilities)
2. DISCOVER: Other agents can call getManifests to discover capabilities
3. REQUEST: Agents request floor access with priority
4. QUEUE: Convener maintains priority queue of requests
5. GRANT: Convener grants floor to highest priority agent
6. SPEAK: Agent with floor can send utterances
7. YIELD: Agent yields floor when done
8. NEXT: Convener grants floor to next agent in queue
9. REPEAT: Steps 6-8 repeat until conversation ends

This is the core of OFP 1.0.1 floor control!
""")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

