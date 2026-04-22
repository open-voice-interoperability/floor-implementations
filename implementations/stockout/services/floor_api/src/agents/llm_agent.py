"""
LLM Agent - Agent with real LLM integration (OpenAI, Anthropic, etc.)
"""

from typing import Optional
import structlog
import os

from src.agents.base_agent import BaseAgent
from src.floor_manager.envelope import (
    OpenFloorEnvelope,
    EventType,
    EventObject,
    ToObject
)

logger = structlog.get_logger()


class LLMAgent(BaseAgent):
    """
    Agent with real LLM integration
    Supports OpenAI, Anthropic, and other providers via LangChain
    """

    def __init__(
        self,
        speakerUri: str,
        agent_name: str,
        llm_provider: str = "openai",  # "openai", "anthropic", "ollama"
        model_name: Optional[str] = None,
        system_prompt: Optional[str] = None,
        serviceUrl: Optional[str] = None,
        agent_version: str = "1.1.0"
    ) -> None:
        """
        Initialize LLM agent

        Args:
            speakerUri: Unique URI identifying the agent
            agent_name: Human-readable agent name
            llm_provider: LLM provider ("openai", "anthropic", "ollama")
            model_name: Model name (e.g., "gpt-4", "claude-3-opus")
            system_prompt: System prompt for the LLM
            serviceUrl: Optional service URL
            agent_version: Agent version
        """
        super().__init__(
            speakerUri=speakerUri,
            agent_name=agent_name,
            serviceUrl=serviceUrl,
            agent_version=agent_version
        ) 

        self.llm_provider = llm_provider.lower()
        self.model_name = model_name or self._get_default_model()
        self.system_prompt = system_prompt or self._get_default_system_prompt()
        self._llm_client = None
        self._conversation_history: dict[str, list] = {}

    def _get_default_model(self) -> str:
        """Get default model for provider"""
        defaults = {
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-haiku-20240307",
            "ollama": "llama3.1"
        }
        return defaults.get(self.llm_provider, "gpt-4o-mini")

    def _get_default_system_prompt(self) -> str:
        """Get default system prompt"""
        return f"""You are {self.agent_name}, a helpful AI assistant participating in a multi-agent conversation.
You communicate using the Open Floor Protocol (OFP) 1.0.0.
Be concise, helpful, and collaborative with other agents in the conversation."""

    def _init_llm_client(self) -> None:
        """Initialize LLM client based on provider"""
        if self._llm_client:
            return

        try:
            if self.llm_provider == "openai":
                from openai import AsyncOpenAI
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError(
                        "OPENAI_API_KEY environment variable not set. "
                        "Set it with: export OPENAI_API_KEY='sk-...'"
                    )
                self._llm_client = AsyncOpenAI(api_key=api_key)
                logger.info(
                    "OpenAI client initialized",
                    model=self.model_name,
                    api_key_set=bool(api_key)
                )

            elif self.llm_provider == "anthropic":
                from anthropic import AsyncAnthropic
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if not api_key:
                    raise ValueError("ANTHROPIC_API_KEY environment variable not set")
                self._llm_client = AsyncAnthropic(api_key=api_key)
                logger.info("Anthropic client initialized", model=self.model_name)

            elif self.llm_provider == "ollama":
                # Ollama uses local HTTP API
                import httpx
                ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
                self._llm_client = {"url": ollama_url, "model": self.model_name}
                logger.info("Ollama client initialized", url=ollama_url, model=self.model_name)

            else:
                raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")

        except ImportError as e:
            logger.error("LLM library not installed", provider=self.llm_provider, error=str(e))
            raise ImportError(
                f"Please install the required library for {self.llm_provider}. "
                f"Example: pip install openai"
            )

    async def _call_openai(
        self,
        conversation_id: str,
        user_message: str
    ) -> str:
        """Call OpenAI API"""
        self._init_llm_client() 

        messages = self._get_conversation_messages(conversation_id, user_message) 

        response = await self._llm_client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0.7
        ) 

        assistant_message = response.choices[0].message.content or "" 
        self._add_to_history(conversation_id, "assistant", assistant_message) 

        return assistant_message 

    async def _call_anthropic(
        self,
        conversation_id: str,
        user_message: str
    ) -> str:
        """Call Anthropic API"""
        self._init_llm_client() 

        messages = self._get_conversation_messages(conversation_id, user_message) 

        response = await self._llm_client.messages.create(
            model=self.model_name,
            max_tokens=1024,
            messages=messages[1:]  # Skip system message (Anthropic uses system parameter)
        ) 

        assistant_message = response.content[0].text 
        self._add_to_history(conversation_id, "assistant", assistant_message) 

        return assistant_message 

    async def _call_ollama(
        self,
        conversation_id: str,
        user_message: str
    ) -> str:
        """Call Ollama API"""
        import httpx 

        self._init_llm_client() 

        messages = self._get_conversation_messages(conversation_id, user_message) 

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._llm_client['url']}/api/chat",
                json={
                    "model": self._llm_client["model"],
                    "messages": messages,
                    "stream": False
                },
                timeout=60.0
            ) 
            response.raise_for_status() 
            result = response.json() 

        assistant_message = result["message"]["content"] 
        self._add_to_history(conversation_id, "assistant", assistant_message) 

        return assistant_message 

    def _get_conversation_messages(
        self,
        conversation_id: str,
        user_message: str
    ) -> list[dict]:
        """Get conversation messages for LLM"""
        messages = [{"role": "system", "content": self.system_prompt}] 

        # Add conversation history
        if conversation_id in self._conversation_history:
            messages.extend(self._conversation_history[conversation_id]) 

        # Add current user message
        messages.append({"role": "user", "content": user_message}) 

        return messages 

    def _add_to_history(
        self,
        conversation_id: str,
        role: str,
        content: str
    ) -> None:
        """Add message to conversation history"""
        if conversation_id not in self._conversation_history:
            self._conversation_history[conversation_id] = [] 

        self._conversation_history[conversation_id].append({
            "role": role,
            "content": content
        }) 

        # Keep last 10 messages to avoid context overflow
        if len(self._conversation_history[conversation_id]) > 10:
            self._conversation_history[conversation_id] = \
                self._conversation_history[conversation_id][-10:] 

    async def handle_envelope(
        self,
        envelope: OpenFloorEnvelope
    ) -> Optional[OpenFloorEnvelope]:
        """
        Handle incoming conversation envelope
        """
        events_for_me = envelope.get_events_for_agent(
            self.speakerUri,
            self.serviceUrl
        ) 

        if not events_for_me:
            return None 

        logger.info(
            "Handling envelope",
            speakerUri=self.speakerUri,
            conversation_id=envelope.conversation.id,
            event_count=len(events_for_me)
        ) 

        response_events = [] 

        for event in events_for_me:
            if event.eventType == EventType.UTTERANCE:
                # Extract utterance text
                utterance_text = "" 
                if (
                    event.parameters
                    and "dialogEvent" in event.parameters
                    and "features" in event.parameters["dialogEvent"]
                    and "text" in event.parameters["dialogEvent"]["features"]
                    and "tokens" in event.parameters["dialogEvent"]["features"]["text"]
                ):
                    tokens = event.parameters["dialogEvent"]["features"]["text"]["tokens"] 
                    utterance_text = " ".join(
                        token.get("token", "") for token in tokens
                    ) 

                # Process with LLM
                response_text = await self.process_utterance(
                    envelope.conversation.id,
                    utterance_text,
                    envelope.sender.speakerUri
                ) 

                if response_text:
                    response_event = EventObject(
                        to=ToObject(
                            speakerUri=envelope.sender.speakerUri,
                            serviceUrl=envelope.sender.serviceUrl
                        ),
                        eventType=EventType.UTTERANCE,
                        parameters={
                            "dialogEvent": {
                                "speakerUri": self.speakerUri,
                                "features": {
                                    "text": {
                                        "mimeType": "text/plain",
                                        "tokens": [{"token": response_text}]
                                    }
                                }
                            }
                        }
                    ) 
                    response_events.append(response_event) 

        if not response_events:
            return None 

        # Create response envelope
        from src.floor_manager.envelope import (
            SchemaObject,
            ConversationObject,
            SenderObject
        )

        response_envelope = OpenFloorEnvelope(
            schema_obj=SchemaObject(version="1.1.0"),
            conversation=ConversationObject(id=envelope.conversation.id),
            sender=SenderObject(
                speakerUri=self.speakerUri,
                serviceUrl=self.serviceUrl
            ),
            events=response_events
        ) 

        return response_envelope

    async def process_utterance(
        self,
        conversation_id: str,
        utterance_text: str,
        sender_speakerUri: str
    ) -> Optional[str]:
        """
        Process utterance using LLM

        Args:
            conversation_id: Conversation identifier
            utterance_text: Text of the utterance
            sender_speakerUri: Speaker URI of the sender

        Returns:
            LLM response text or None
        """
        logger.info(
            "Processing utterance with LLM",
            speakerUri=self.speakerUri,
            conversation_id=conversation_id,
            provider=self.llm_provider,
            model=self.model_name
        ) 

        try:
            # Add user message to history
            self._add_to_history(conversation_id, "user", utterance_text) 

            # Call appropriate LLM provider
            if self.llm_provider == "openai":
                response = await self._call_openai(conversation_id, utterance_text) 
            elif self.llm_provider == "anthropic":
                response = await self._call_anthropic(conversation_id, utterance_text) 
            elif self.llm_provider == "ollama":
                response = await self._call_ollama(conversation_id, utterance_text) 
            else:
                raise ValueError(f"Unsupported provider: {self.llm_provider}") 

            logger.info(
                "LLM response generated",
                speakerUri=self.speakerUri,
                response_length=len(response)
            ) 

            return response 

        except Exception as e:
            logger.error(
                "Error calling LLM",
                speakerUri=self.speakerUri,
                provider=self.llm_provider,
                error=str(e)
            ) 
            return f"I apologize, but I encountered an error: {str(e)}" 

