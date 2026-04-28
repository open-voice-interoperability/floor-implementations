"""
Example: How to use LLM Agent with real LLM providers (OpenAI, Ollama)

This example shows how to create agents that use real LLM models instead of fake echo responses.
"""

import asyncio
import os
import sys

# Add parent directory to path so we can import src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.agents.llm_agent import LLMAgent
from src.floor_manager.envelope import (
    OpenFloorEnvelope,
    SchemaObject,
    ConversationObject,
    SenderObject,
    EventObject,
    EventType,
    ToObject
)


async def example_openai_agent():
    """
    Example: Create an agent using OpenAI GPT models
    """
    print("=" * 60)
    print("Example: OpenAI Agent")
    print("=" * 60)

    # OpenAI API key should be set as environment variable
    # The code automatically reads from: $OPENAI_API_KEY
    # Set it with: export OPENAI_API_KEY="sk-..."
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n⚠️  OPENAI_API_KEY not set!")
        print("Please set it: export OPENAI_API_KEY='sk-...'")
        print("Or add to .env file: OPENAI_API_KEY=sk-...")
        return
    
    # Show that we found the key (partial for security)
    key_preview = api_key[:7] + "..." if len(api_key) > 7 else "***"
    print(f"\n✅ Using OPENAI_API_KEY: {key_preview}")

    # Create OpenAI agent
    agent = LLMAgent(
        speakerUri="tag:example.com,2025:openai_agent",
        agent_name="OpenAI Assistant",
        llm_provider="openai",
        model_name="gpt-4o-mini",  # or "gpt-4", "gpt-3.5-turbo", etc.
        system_prompt="You are a helpful assistant in a multi-agent conversation."
    )

    # Simulate receiving a message
    conversation_id = "conv_llm_test"
    test_message = "Hello! Can you help me understand how floor control works?"

    print(f"\n📨 Received message: {test_message}")
    print("\n🤖 Processing with OpenAI...")

    response = await agent.process_utterance(
        conversation_id=conversation_id,
        utterance_text=test_message,
        sender_speakerUri="tag:example.com,2025:user"
    )

    print(f"\n💬 Agent response: {response}")

    await agent.stop()


async def example_openai_agent_gpt4():
    """
    Example: Create an agent using OpenAI GPT-4 (more capable model)
    """
    print("\n" + "=" * 60)
    print("Example: OpenAI GPT-4 Agent")
    print("=" * 60)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n⚠️  OPENAI_API_KEY not set!")
        print("Please set it: export OPENAI_API_KEY='sk-...'")
        return

    key_preview = api_key[:7] + "..." if len(api_key) > 7 else "***"
    print(f"\n✅ Using OPENAI_API_KEY: {key_preview}")

    agent = LLMAgent(
        speakerUri="tag:example.com,2025:gpt4_agent",
        agent_name="GPT-4 Assistant",
        llm_provider="openai",
        model_name="gpt-4o",  # More capable model
        system_prompt="You are an expert assistant specializing in multi-agent systems and floor control protocols."
    )

    conversation_id = "conv_gpt4_test"
    test_message = "Explain the concept of floor control in multi-agent systems."

    print(f"\n📨 Received message: {test_message}")
    print("\n🤖 Processing with GPT-4o...")

    response = await agent.process_utterance(
        conversation_id=conversation_id,
        utterance_text=test_message,
        sender_speakerUri="tag:example.com,2025:user"
    )

    print(f"\n💬 Agent response: {response}")

    await agent.stop()


async def example_ollama_agent():
    """
    Example: Create an agent using Ollama (local LLM)
    
    Requires Ollama to be running locally:
    - Install: https://ollama.ai
    - Run: ollama serve
    - Pull model: ollama pull llama3.1
    """
    print("\n" + "=" * 60)
    print("Example: Ollama Agent (Local LLM)")
    print("=" * 60)

    agent = LLMAgent(
        speakerUri="tag:example.com,2025:ollama_agent",
        agent_name="Local LLM Assistant",
        llm_provider="ollama",
        model_name="llama3.1",  # Using llama3.1:latest
        system_prompt="You are a helpful assistant in a multi-agent conversation."
    )

    conversation_id = "conv_ollama_test"
    test_message = "Hello! What can you do?"

    print(f"\n📨 Received message: {test_message}")
    print("\n🤖 Processing with Ollama...")
    print("(Make sure Ollama is running: ollama serve)")

    try:
        response = await agent.process_utterance(
            conversation_id=conversation_id,
            utterance_text=test_message,
            sender_speakerUri="tag:example.com,2025:user"
        )
        print(f"\n💬 Agent response: {response}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("Make sure Ollama is running: ollama serve")

    await agent.stop()


async def example_multi_llm_conversation():
    """
    Example: Multiple LLM agents having a conversation
    """
    print("\n" + "=" * 60)
    print("Example: Multi-LLM Agent Conversation")
    print("=" * 60)

    # Check API keys
    has_openai = bool(os.getenv("OPENAI_API_KEY"));

    if not has_openai:
        print("\n⚠️  OPENAI_API_KEY not set!")
        print("Set it: export OPENAI_API_KEY='sk-...'")
        return

    agents = [];

    # First agent: GPT-4o-mini (fast and cheap)
    agent1 = LLMAgent(
        speakerUri="tag:example.com,2025:gpt_mini_agent",
        agent_name="GPT-4o-mini Assistant",
        llm_provider="openai",
        model_name="gpt-4o-mini",
        system_prompt="You are GPT-4o-mini, a helpful assistant. Be concise."
    );
    agents.append(agent1);

    # Second agent: GPT-4o (more capable)
    agent2 = LLMAgent(
        speakerUri="tag:example.com,2025:gpt4_agent",
        agent_name="GPT-4o Assistant",
        llm_provider="openai",
        model_name="gpt-4o",
        system_prompt="You are GPT-4o, a more capable assistant. Provide detailed answers."
    );
    agents.append(agent2);

    if not agents:
        return;

    conversation_id = "conv_multi_llm";

    # Agent 1 asks a question
    if agents:
        question = "What is the capital of France?";
        print(f"\n💬 {agents[0].agent_name}: {question}");

        response = await agents[0].process_utterance(
            conversation_id=conversation_id,
            utterance_text=question,
            sender_speakerUri="tag:example.com,2025:user"
        );
        print(f"🤖 {agents[0].agent_name}: {response}");

        # Agent 2 responds (if available)
        if len(agents) > 1:
            follow_up = f"Based on that, what is a famous landmark in {response.split()[-1].rstrip('?.!')}?";
            print(f"\n💬 {agents[1].agent_name}: {follow_up}");

            response2 = await agents[1].process_utterance(
                conversation_id=conversation_id,
                utterance_text=follow_up,
                sender_speakerUri=agents[0].speakerUri
            );
            print(f"🤖 {agents[1].agent_name}: {response2}");

    # Cleanup
    for agent in agents:
        await agent.stop();


async def main():
    """Run examples"""
    print("\n🚀 LLM Agent Examples")
    print("=" * 60)
    print("\nThis script demonstrates how to use real LLM providers")
    print("with Open Floor Protocol agents.\n")

    # Example 1: OpenAI GPT-4o-mini
    await example_openai_agent();

    # Example 2: OpenAI GPT-4o
    await example_openai_agent_gpt4();

    # Example 3: Ollama (local)
    await example_ollama_agent();

    # Example 4: Multi-LLM conversation
    await example_multi_llm_conversation();

    print("\n" + "=" * 60)
    print("✅ Examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main());

