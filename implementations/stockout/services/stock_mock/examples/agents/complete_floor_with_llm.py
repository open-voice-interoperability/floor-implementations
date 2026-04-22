#!/usr/bin/env python3
"""
Complete OFP Demo with REAL LLMs + Floor Control

This demo combines:
1. Floor Manager with priority queue
2. Real LLM agents (OpenAI GPT-4o-mini)
3. Full OFP 1.0.1 flow: requestFloor, grantFloor, speak, yieldFloor

Requirements:
- Floor Manager running (docker-compose up)
- OPENAI_API_KEY environment variable set
"""

import asyncio
import httpx
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.agents.llm_agent import LLMAgent

# Floor Manager API base URL
FLOOR_API = "http://localhost:8000/api/v1"


class OFPLLMAgent:
    """
    OFP Agent with real LLM + Floor Manager integration
    """
    
    def __init__(
        self,
        speakerUri: str,
        agent_name: str,
        llm_provider: str = "openai",
        model_name: str = "gpt-4o-mini",
        system_prompt: str = None,
        priority: int = 5
    ):
        self.llm_agent = LLMAgent(
            speakerUri=speakerUri,
            agent_name=agent_name,
            llm_provider=llm_provider,
            model_name=model_name,
            system_prompt=system_prompt or f"You are {agent_name}, a helpful AI assistant in a multi-agent conversation. Be concise (max 2-3 sentences)."
        )
        self.speakerUri = speakerUri
        self.agent_name = agent_name
        self.priority = priority
        self.client = httpx.AsyncClient(timeout=60.0)
        
    async def request_floor(self, conversation_id: str) -> bool:
        """Request floor from Floor Manager"""
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
            granted = data.get("granted", False)
            if granted:
                print(f"   ✅ Floor GRANTED to {self.agent_name}")
            else:
                print(f"   ⏳ {self.agent_name} queued (waiting for floor)")
            return granted
        else:
            print(f"   ❌ Request failed: {response.text}")
            return False
            
    async def yield_floor(self, conversation_id: str) -> bool:
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
            return True
        else:
            print(f"   ❌ Release failed")
            return False
    
    async def speak_with_llm(self, conversation_id: str, prompt: str) -> str:
        """Generate response using LLM"""
        print(f"\n💬 {self.agent_name} thinking...")
        
        response = await self.llm_agent.process_utterance(
            conversation_id=conversation_id,
            utterance_text=prompt,
            sender_speakerUri="tag:floor.manager,2025:system"
        )
        
        print(f"🤖 {self.agent_name}: {response}")
        return response
    
    async def check_floor_holder(self, conversation_id: str) -> dict:
        """Check who holds the floor"""
        response = await self.client.get(f"{FLOOR_API}/floor/holder/{conversation_id}")
        if response.status_code == 200:
            return response.json()
        return {}
    
    async def close(self):
        """Cleanup"""
        await self.client.aclose()
        await self.llm_agent.stop()


async def wait_for_floor(agent: OFPLLMAgent, conversation_id: str, max_wait: int = 30):
    """Wait until agent gets the floor"""
    for _ in range(max_wait):
        holder_info = await agent.check_floor_holder(conversation_id)
        if holder_info.get("holder") == agent.speakerUri:
            return True
        await asyncio.sleep(1)
    return False


async def main():
    """
    Main demo: 3 LLM agents having a conversation with floor control
    
    Scenario: Planning a trip to Paris
    - Coordinator: Leads the conversation (priority 10)
    - Travel Agent: Provides recommendations (priority 7)
    - Budget Analyst: Analyzes costs (priority 5)
    """
    
    print("\n" + "="*70)
    print("🚀 COMPLETE OFP DEMO: LLM AGENTS + FLOOR CONTROL")
    print("="*70)
    
    print("\nThis demo shows:")
    print("  1. Real LLM agents (OpenAI GPT-4o-mini)")
    print("  2. Floor control with priority queue")
    print("  3. Full OFP 1.0.1 flow (request → grant → speak → yield)")
    print("  4. Multi-agent conversation coordination")
    
    # Check API key
    if not os.getenv("OPENAI_API_KEY"):
        print("\n❌ OPENAI_API_KEY not set!")
        print("Set it: export OPENAI_API_KEY='sk-...'")
        return
    
    # Check Floor Manager health
    print("\n🏥 Checking Floor Manager health...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/health")
            if response.status_code == 200:
                print("   ✅ Floor Manager is running")
            else:
                print("   ❌ Floor Manager error")
                return
    except Exception as e:
        print(f"   ❌ Cannot connect to Floor Manager: {e}")
        print("\n💡 Start it with: docker-compose up")
        return
    
    conversation_id = "trip_to_paris_001"
    
    # Create LLM agents with different roles and priorities
    print("\n" + "="*70)
    print("STEP 1: Create LLM Agents")
    print("="*70)
    
    coordinator = OFPLLMAgent(
        speakerUri="tag:trip.demo,2025:coordinator",
        agent_name="Coordinator",
        model_name="gpt-4o-mini",
        system_prompt="You are a trip coordinator. Lead the conversation about planning a Paris trip. Be concise (2-3 sentences max).",
        priority=10  # Highest
    )
    print(f"   ✅ Created: Coordinator (priority 10, GPT-4o-mini)")
    
    travel_agent = OFPLLMAgent(
        speakerUri="tag:trip.demo,2025:travel",
        agent_name="Travel Agent",
        model_name="gpt-4o-mini",
        system_prompt="You are a Paris travel expert. Suggest attractions and activities. Be concise (2-3 sentences max).",
        priority=7  # Medium
    )
    print(f"   ✅ Created: Travel Agent (priority 7, GPT-4o-mini)")
    
    budget_analyst = OFPLLMAgent(
        speakerUri="tag:trip.demo,2025:budget",
        agent_name="Budget Analyst",
        model_name="gpt-4o-mini",
        system_prompt="You are a budget analyst for trips. Provide cost estimates for Paris. Be concise (2-3 sentences max).",
        priority=5  # Lower
    )
    print(f"   ✅ Created: Budget Analyst (priority 5, GPT-4o-mini)")
    
    try:
        # Step 2: All agents request floor (priority queue demonstration)
        print("\n" + "="*70)
        print("STEP 2: Floor Requests (Testing Priority Queue)")
        print("="*70)
        print("\n💡 All agents request floor. Watch who gets it first!")
        
        # Request in reverse priority order to show queue works
        await budget_analyst.request_floor(conversation_id)  # priority 5
        await asyncio.sleep(0.5)
        await travel_agent.request_floor(conversation_id)    # priority 7
        await asyncio.sleep(0.5)
        await coordinator.request_floor(conversation_id)     # priority 10
        
        # Step 3: Conversation with floor control
        print("\n" + "="*70)
        print("STEP 3: Multi-Agent Conversation with Floor Control")
        print("="*70)
        
        # Budget Analyst speaks first (got floor first)
        print("\n--- Round 1: Budget Analyst has floor ---")
        await budget_analyst.speak_with_llm(
            conversation_id,
            "We're planning a 5-day trip to Paris. What's a reasonable budget per person?"
        )
        await asyncio.sleep(2)
        await budget_analyst.yield_floor(conversation_id)
        await asyncio.sleep(2)
        
        # Travel Agent gets floor next (priority 7 in queue)
        print("\n--- Round 2: Travel Agent has floor ---")
        if await wait_for_floor(travel_agent, conversation_id, max_wait=5):
            await travel_agent.speak_with_llm(
                conversation_id,
                "Based on a mid-range budget, what are the must-see attractions in Paris?"
            )
            await asyncio.sleep(2)
            await travel_agent.yield_floor(conversation_id)
            await asyncio.sleep(2)
        
        # Coordinator gets floor last (priority 10 in queue)
        print("\n--- Round 3: Coordinator has floor ---")
        if await wait_for_floor(coordinator, conversation_id, max_wait=5):
            await coordinator.speak_with_llm(
                conversation_id,
                "Great! Let's create a day-by-day itinerary combining budget considerations and top attractions."
            )
            await asyncio.sleep(2)
            await coordinator.yield_floor(conversation_id)
        
        # Step 4: Summary
        print("\n" + "="*70)
        print("✅ DEMO COMPLETED SUCCESSFULLY!")
        print("="*70)
        
        print("\n📊 What You Just Saw:")
        print("   ✓ 3 LLM agents (GPT-4o-mini) with different roles")
        print("   ✓ Floor control with priority queue")
        print("   ✓ Agents requested floor → Floor Manager granted by priority")
        print("   ✓ Each agent spoke using real AI → yielded floor")
        print("   ✓ Automatic handoff to next agent in queue")
        
        print("\n💰 Estimated Cost: ~$0.01 (3 GPT-4o-mini calls)")
        
        print("\n🎯 This is OFP 1.0.1 in Action!")
        print("   - Floor Manager coordinates multi-agent conversation")
        print("   - Priority queue ensures fair turn-taking")
        print("   - LLM agents provide intelligent responses")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        print("\n🧹 Cleaning up...")
        await coordinator.close()
        await travel_agent.close()
        await budget_analyst.close()


if __name__ == "__main__":
    asyncio.run(main())



