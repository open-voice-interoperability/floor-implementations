#!/usr/bin/env python3
"""
Quick test to verify LLM integration works with your API key

This script checks if your OPENAI_API_KEY is set and tests a simple LLM call.
"""

import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.agents.llm_agent import LLMAgent


async def test_openai_agent():
    """Quick test of OpenAI agent"""
    print("=" * 60)
    print("Quick LLM Agent Test")
    print("=" * 60)
    print()

    # Check if API key is set
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ ERROR: OPENAI_API_KEY environment variable not set!")
        print()
        print("Set it with:")
        print("  export OPENAI_API_KEY='sk-...'")
        print()
        print("Or add to your .env file:")
        print("  OPENAI_API_KEY=sk-...")
        return False

    # Show partial key for verification (first 7 chars + ...)
    key_preview = api_key[:7] + "..." if len(api_key) > 7 else "***"
    print(f"✅ OPENAI_API_KEY found: {key_preview}")
    print()

    try:
        # Create agent
        print("🤖 Creating LLM agent...")
        agent = LLMAgent(
            speakerUri="tag:test.com,2025:test_agent",
            agent_name="Test Agent",
            llm_provider="openai",
            model_name="gpt-4o-mini"  # Cheap and fast model for testing
        )
        print("✅ Agent created")
        print()

        # Test simple message
        print("💬 Sending test message...")
        test_message = "Say 'Hello from OpenAI!' in one sentence."
        print(f"   Message: {test_message}")
        print()

        response = await agent.process_utterance(
            conversation_id="test_conv",
            utterance_text=test_message,
            sender_speakerUri="tag:test.com,2025:user"
        )

        print("✅ Response received:")
        print(f"   {response}")
        print()

        # Test conversation history
        print("💬 Testing conversation history...")
        follow_up = "Now say 'This is a follow-up message'"
        print(f"   Follow-up: {follow_up}")
        print()

        response2 = await agent.process_utterance(
            conversation_id="test_conv",  # Same conversation ID
            utterance_text=follow_up,
            sender_speakerUri="tag:test.com,2025:user"
        )

        print("✅ Follow-up response:")
        print(f"   {response2}")
        print()

        await agent.stop()

        print("=" * 60)
        print("✅ All tests passed! LLM integration is working.")
        print("=" * 60)
        return True

    except ImportError as e:
        print(f"❌ ERROR: Missing dependency")
        print(f"   {e}")
        print()
        print("Install with:")
        print("  pip install openai")
        return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        print()
        print("Check:")
        print("  1. API key is valid")
        print("  2. You have credits/quota")
        print("  3. Internet connection is working")
        return False


async def main():
    """Run test"""
    success = await test_openai_agent()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())







