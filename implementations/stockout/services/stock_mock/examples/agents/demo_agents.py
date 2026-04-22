"""
Demo Agents - Example agents to test the Floor Manager
"""

import asyncio
import httpx
import json
from typing import Optional
from datetime import datetime


class DemoAgent:
    """
    Demo agent that connects to Floor Manager via REST API
    """

    def __init__(
        self,
        speaker_uri: str,
        agent_name: str,
        capabilities: list[str],
        floor_api_url: str = "http://localhost:8000",
        service_url: Optional[str] = None
    ):
        self.speaker_uri = speaker_uri
        self.agent_name = agent_name
        self.capabilities = capabilities
        self.floor_api_url = floor_api_url
        self.service_url = service_url or f"http://localhost:8000"
        self.client = httpx.AsyncClient(timeout=30.0)

    async def register(self) -> bool:
        """Register the agent in the registry"""
        try:
            response = await self.client.post(
                f"{self.floor_api_url}/api/v1/agents/register",
                json={
                    "speakerUri": self.speaker_uri,
                    "agent_name": self.agent_name,
                    "capabilities": self.capabilities,
                    "serviceUrl": self.service_url
                }
            )
            response.raise_for_status()
            print(f"✅ {self.agent_name} registered successfully")
            return True
        except Exception as e:
            print(f"❌ Registration error for {self.agent_name}: {e}")
            return False

    async def request_floor(self, conversation_id: str, priority: int = 5) -> bool:
        """Request floor for a conversation"""
        try:
            response = await self.client.post(
                f"{self.floor_api_url}/api/v1/floor/request",
                json={
                    "conversation_id": conversation_id,
                    "speakerUri": self.speaker_uri,
                    "priority": priority
                }
            )
            response.raise_for_status()
            data = response.json()
            if data.get("granted"):
                print(f"🎤 {self.agent_name} obtained the floor")
            else:
                print(f"⏳ {self.agent_name} is queued for the floor")
            return data.get("granted", False)
        except Exception as e:
            print(f"❌ Floor request error for {self.agent_name}: {e}")
            return False

    async def release_floor(self, conversation_id: str) -> bool:
        """Release the floor"""
        try:
            response = await self.client.post(
                f"{self.floor_api_url}/api/v1/floor/release",
                json={
                    "conversation_id": conversation_id,
                    "speakerUri": self.speaker_uri
                }
            )
            response.raise_for_status()
            print(f"🔓 {self.agent_name} released the floor")
            return True
        except Exception as e:
            print(f"❌ Floor release error for {self.agent_name}: {e}")
            return False

    async def send_utterance(
        self,
        conversation_id: str,
        target_speaker_uri: Optional[str],
        text: str
    ) -> bool:
        """Send an utterance"""
        try:
            response = await self.client.post(
                f"{self.floor_api_url}/api/v1/envelopes/utterance",
                json={
                    "conversation_id": conversation_id,
                    "sender_speakerUri": self.speaker_uri,
                    "target_speakerUri": target_speaker_uri,
                    "text": text
                }
            )
            response.raise_for_status()
            print(f"💬 {self.agent_name}: {text}")
            return True
        except Exception as e:
            print(f"❌ Utterance send error for {self.agent_name}: {e}")
            return False

    async def get_floor_holder(self, conversation_id: str) -> Optional[str]:
        """Get current floor holder"""
        try:
            response = await self.client.get(
                f"{self.floor_api_url}/api/v1/floor/holder/{conversation_id}"
            )
            response.raise_for_status()
            data = response.json()
            return data.get("holder")
        except Exception as e:
            print(f"❌ Error getting floor holder: {e}")
            return None

    async def heartbeat(self) -> bool:
        """Update heartbeat"""
        try:
            response = await self.client.post(
                f"{self.floor_api_url}/api/v1/agents/heartbeat",
                json={"speakerUri": self.speaker_uri}
            )
            response.raise_for_status()
            return True
        except Exception as e:
            return False

    async def close(self):
        """Close connection"""
        await self.client.aclose()


async def demo_multi_agent_conversation():
    """
    Demo: Multi-agent conversation with floor control
    
    This demo shows:
    1. How agents request floor with different priorities
    2. How floor queue works (higher priority agents get floor first)
    3. How agents can send messages even without floor (but can't respond)
    4. How floor is passed to the next agent in queue when released
    """
    print("=" * 60)
    print("DEMO: Multi-Agent Conversation with Floor Control")
    print("=" * 60)
    print()

    # Create demo agents
    text_agent = DemoAgent(
        speaker_uri="tag:demo.com,2025:text_agent",
        agent_name="Text Agent",
        capabilities=["text_generation"]
    )

    image_agent = DemoAgent(
        speaker_uri="tag:demo.com,2025:image_agent",
        agent_name="Image Agent",
        capabilities=["image_generation"]
    )

    data_agent = DemoAgent(
        speaker_uri="tag:demo.com,2025:data_agent",
        agent_name="Data Agent",
        capabilities=["data_analysis"]
    )

    conversation_id = f"conv_demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    try:
        # Register agents
        print("📝 Registering agents...")
        await text_agent.register()
        await image_agent.register()
        await data_agent.register()
        print()

        # Test floor control
        print("🎤 Floor Control Test:")
        print("-" * 60)

        # Agent 1 requests floor
        print("\n1. Text Agent requests floor (priority 5)...")
        await text_agent.request_floor(conversation_id, priority=5)
        holder = await text_agent.get_floor_holder(conversation_id)
        print(f"   Floor holder: {holder}")

        # Agent 2 requests floor (will be queued)
        print("\n2. Image Agent requests floor (priority 4)...")
        await image_agent.request_floor(conversation_id, priority=4)
        holder = await text_agent.get_floor_holder(conversation_id)
        print(f"   Floor holder: {holder} (Image Agent is queued)")

        # Agent 3 requests floor (will be queued with lower priority)
        print("\n3. Data Agent requests floor (priority 3)...")
        await data_agent.request_floor(conversation_id, priority=3)
        holder = await text_agent.get_floor_holder(conversation_id)
        print(f"   Floor holder: {holder} (Data Agent is queued after Image Agent)")

        # Agent 1 sends utterance to Image Agent
        print("\n4. Text Agent sends utterance to Image Agent...")
        await text_agent.send_utterance(
            conversation_id,
            image_agent.speaker_uri,
            "Hello Image Agent, can you generate an image?"
        )
        print("   Note: Image Agent receives the message but cannot respond yet (no floor)")

        # Agent 1 releases floor
        print("\n5. Text Agent releases floor...")
        await text_agent.release_floor(conversation_id)
        await asyncio.sleep(1)  # Wait for queue processing
        holder = await text_agent.get_floor_holder(conversation_id)
        print(f"   New floor holder: {holder}")
        print("   (Image Agent gets floor because it has highest priority in queue)")

        # Image Agent responds now that it has the floor
        if holder == image_agent.speaker_uri:
            print("\n6. Image Agent responds (now has floor)...")
            await image_agent.send_utterance(
                conversation_id,
                text_agent.speaker_uri,
                "Certainly! I'm generating the image for you..."
            )
            
            # Image Agent releases floor
            print("\n7. Image Agent releases floor...")
            await image_agent.release_floor(conversation_id)
            await asyncio.sleep(1)
            holder = await text_agent.get_floor_holder(conversation_id)
            print(f"   New floor holder: {holder}")
            
            if holder == data_agent.speaker_uri:
                print("\n8. Data Agent gets floor (next in queue)...")
                await data_agent.send_utterance(
                    conversation_id,
                    None,  # Broadcast
                    "I can analyze the data if needed..."
                )
        elif holder == data_agent.speaker_uri:
            print("\n6. Data Agent gets floor (higher priority in queue)...")
            await data_agent.send_utterance(
                conversation_id,
                None,
                "I can analyze the data if needed..."
            )

        print("\n" + "=" * 60)
        print("✅ Demo completed successfully!")
        print("=" * 60)

    finally:
        # Cleanup
        await text_agent.close()
        await image_agent.close()
        await data_agent.close()


async def demo_floor_priority():
    """
    Demo: Test priority in floor control
    """
    print("=" * 60)
    print("DEMO: Floor Control Priority Test")
    print("=" * 60)
    print()

    agent1 = DemoAgent(
        speaker_uri="tag:demo.com,2025:agent_1",
        agent_name="Agent 1 (Priority 3)",
        capabilities=["text_generation"]
    )

    agent2 = DemoAgent(
        speaker_uri="tag:demo.com,2025:agent_2",
        agent_name="Agent 2 (Priority 5)",
        capabilities=["text_generation"]
    )

    conversation_id = f"conv_priority_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    try:
        await agent1.register()
        await agent2.register()

        print("Agent 1 requests floor with priority 3...")
        await agent1.request_floor(conversation_id, priority=3)
        await asyncio.sleep(0.5)

        print("Agent 2 requests floor with priority 5 (higher)...")
        await agent2.request_floor(conversation_id, priority=5)
        await asyncio.sleep(0.5)

        holder = await agent1.get_floor_holder(conversation_id)
        print(f"\nCurrent floor holder: {holder}")
        print("Note: Agent 2 has higher priority but Agent 1 already has the floor")

        print("\nAgent 1 releases floor...")
        await agent1.release_floor(conversation_id)
        await asyncio.sleep(1)

        holder = await agent1.get_floor_holder(conversation_id)
        print(f"New floor holder: {holder}")
        print("(Should be Agent 2 due to higher priority)")

    finally:
        await agent1.close()
        await agent2.close()


async def demo_simple_conversation():
    """
    Demo: Simple two-agent conversation showing floor passing
    
    This demonstrates a clearer scenario where Agent 1 asks Agent 2,
    and Agent 2 responds when it gets the floor.
    """
    print("=" * 60)
    print("DEMO: Simple Two-Agent Conversation")
    print("=" * 60)
    print()

    agent1 = DemoAgent(
        speaker_uri="tag:demo.com,2025:agent_1",
        agent_name="Agent 1",
        capabilities=["text_generation"]
    )

    agent2 = DemoAgent(
        speaker_uri="tag:demo.com,2025:agent_2",
        agent_name="Agent 2",
        capabilities=["text_generation"]
    )

    conversation_id = f"conv_simple_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    try:
        await agent1.register()
        await agent2.register()

        print("1. Agent 1 requests floor...")
        await agent1.request_floor(conversation_id, priority=5)
        
        print("\n2. Agent 2 requests floor (will be queued)...")
        await agent2.request_floor(conversation_id, priority=4)
        
        print("\n3. Agent 1 sends question to Agent 2...")
        await agent1.send_utterance(
            conversation_id,
            agent2.speaker_uri,
            "Hello Agent 2, can you help me?"
        )
        print("   Note: Agent 2 receives the message but cannot respond (no floor)")
        
        print("\n4. Agent 1 releases floor...")
        await agent1.release_floor(conversation_id)
        await asyncio.sleep(1)
        
        holder = await agent1.get_floor_holder(conversation_id)
        print(f"   Floor holder: {holder}")
        
        if holder == agent2.speaker_uri:
            print("\n5. Agent 2 now has floor and can respond...")
            await agent2.send_utterance(
                conversation_id,
                agent1.speaker_uri,
                "Yes, I can help! What do you need?"
            )
            
            print("\n6. Agent 2 releases floor...")
            await agent2.release_floor(conversation_id)

        print("\n" + "=" * 60)
        print("✅ Demo completed successfully!")
        print("=" * 60)

    finally:
        await agent1.close()
        await agent2.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "priority":
            asyncio.run(demo_floor_priority())
        elif sys.argv[1] == "simple":
            asyncio.run(demo_simple_conversation())
        else:
            print("Usage: python demo_agents.py [priority|simple]")
            print("  No args: Multi-agent demo")
            print("  priority: Priority test demo")
            print("  simple: Simple two-agent conversation")
    else:
        asyncio.run(demo_multi_agent_conversation())
