#!/usr/bin/env python3
"""
Standalone LLM Agent - Works without full project dependencies

This is a simplified version that only needs:
- httpx (for HTTP calls)
- openai or anthropic (for LLM)
- structlog (for logging, optional)

Install minimal dependencies:
  pip install httpx structlog openai
"""

import asyncio
import os
import sys
from typing import Optional

# Try to import LLM libraries
try:
    from openai import AsyncOpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    from anthropic import AsyncAnthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import structlog
    logger = structlog.get_logger()
except ImportError:
    # Fallback to print if structlog not available
    class SimpleLogger:
        def info(self, *args, **kwargs):
            print(f"[INFO] {args}")
        def error(self, *args, **kwargs):
            print(f"[ERROR] {args}")
    logger = SimpleLogger()


class StandaloneLLMAgent:
    """
    Standalone LLM agent that doesn't require the full project setup
    """

    def __init__(
        self,
        agent_name: str,
        llm_provider: str = "openai",
        model_name: Optional[str] = None,
        system_prompt: Optional[str] = None
    ):
        """
        Initialize standalone LLM agent

        Args:
            agent_name: Name of the agent
            llm_provider: "openai" or "anthropic"
            model_name: Model to use (defaults provided)
            system_prompt: System prompt for the LLM
        """
        self.agent_name = agent_name
        self.llm_provider = llm_provider.lower()
        self.model_name = model_name or self._get_default_model()
        self.system_prompt = system_prompt or f"You are {agent_name}, a helpful AI assistant."
        self._llm_client = None
        self._conversation_history: dict[str, list] = {}

    def _get_default_model(self) -> str:
        """Get default model for provider"""
        defaults = {
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-haiku-20240307"
        }
        return defaults.get(self.llm_provider, "gpt-4o-mini")

    def _init_llm_client(self) -> None:
        """Initialize LLM client"""
        if self._llm_client:
            return

        if self.llm_provider == "openai":
            if not HAS_OPENAI:
                raise ImportError("openai library not installed. Run: pip install openai")
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            self._llm_client = AsyncOpenAI(api_key=api_key)
            logger.info("OpenAI client initialized", model=self.model_name)

        elif self.llm_provider == "anthropic":
            if not HAS_ANTHROPIC:
                raise ImportError("anthropic library not installed. Run: pip install anthropic")
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY environment variable not set")
            self._llm_client = AsyncAnthropic(api_key=api_key)
            logger.info("Anthropic client initialized", model=self.model_name)

        else:
            raise ValueError(f"Unsupported provider: {self.llm_provider}")

    async def process_message(
        self,
        conversation_id: str,
        user_message: str
    ) -> str:
        """
        Process a message using LLM

        Args:
            conversation_id: Conversation identifier
            user_message: User's message

        Returns:
            LLM response
        """
        self._init_llm_client()

        # Build messages
        messages = [{"role": "system", "content": self.system_prompt}]

        # Add conversation history
        if conversation_id in self._conversation_history:
            messages.extend(self._conversation_history[conversation_id])

        # Add current message
        messages.append({"role": "user", "content": user_message})

        # Call LLM
        try:
            if self.llm_provider == "openai":
                response = await self._llm_client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=0.7
                )
                assistant_message = response.choices[0].message.content or ""

            elif self.llm_provider == "anthropic":
                response = await self._llm_client.messages.create(
                    model=self.model_name,
                    max_tokens=1024,
                    messages=messages[1:]  # Skip system message
                )
                assistant_message = response.content[0].text

            else:
                raise ValueError(f"Unsupported provider: {self.llm_provider}")

            # Update history
            if conversation_id not in self._conversation_history:
                self._conversation_history[conversation_id] = []

            self._conversation_history[conversation_id].append({
                "role": "user",
                "content": user_message
            })
            self._conversation_history[conversation_id].append({
                "role": "assistant",
                "content": assistant_message
            })

            # Keep last 10 messages
            if len(self._conversation_history[conversation_id]) > 10:
                self._conversation_history[conversation_id] = \
                    self._conversation_history[conversation_id][-10:]

            return assistant_message

        except Exception as e:
            logger.error("Error calling LLM", error=str(e))
            return f"I apologize, but I encountered an error: {str(e)}"


async def main():
    """Test standalone LLM agent"""
    print("=" * 60)
    print("Standalone LLM Agent Test")
    print("=" * 60)
    print()

    # Check API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ ERROR: OPENAI_API_KEY not set!")
        print("Set it with: export OPENAI_API_KEY='sk-...'")
        return

    key_preview = api_key[:7] + "..." if len(api_key) > 7 else "***"
    print(f"✅ Using OPENAI_API_KEY: {key_preview}")
    print()

    # Check if openai is installed
    if not HAS_OPENAI:
        print("❌ ERROR: openai library not installed!")
        print("Install with: pip install openai")
        return

    try:
        # Create agent
        print("🤖 Creating LLM agent...")
        agent = StandaloneLLMAgent(
            agent_name="Test Assistant",
            llm_provider="openai",
            model_name="gpt-4o-mini"
        )
        print("✅ Agent created")
        print()

        # Test message
        print("💬 Sending test message...")
        test_message = "Say 'Hello from OpenAI!' in one sentence."
        print(f"   Message: {test_message}")
        print()

        response = await agent.process_message(
            conversation_id="test_conv",
            user_message=test_message
        )

        print("✅ Response received:")
        print(f"   {response}")
        print()

        # Test conversation
        print("💬 Testing conversation...")
        follow_up = "Now say 'This is a follow-up'"
        print(f"   Follow-up: {follow_up}")
        print()

        response2 = await agent.process_message(
            conversation_id="test_conv",
            user_message=follow_up
        )

        print("✅ Follow-up response:")
        print(f"   {response2}")
        print()

        print("=" * 60)
        print("✅ Test completed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())







