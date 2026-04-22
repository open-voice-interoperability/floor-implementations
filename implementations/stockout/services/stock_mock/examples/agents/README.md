# Agent Examples - OFP 1.1 Compliant

This directory contains example agents demonstrating the Open Floor Protocol 1.1.

## 🎯 Quick Start - Complete OFP Demo

**RECOMMENDED**: Start here to see the full OFP 1.1 protocol in action:

```bash
# Make sure Floor Manager is running
docker-compose up -d

# Run complete OFP demo
python examples/agents/complete_ofp_demo_simple.py
```

**What it demonstrates**:
- ✅ Agents identified only by speakerUri (NO registration per OFP 1.1)
- ✅ Floor Manager makes autonomous floor control decisions
- ✅ Priority-based floor request queue
- ✅ Floor yield and handoff between agents

See [COMPLETE_OFP_DEMO.md](COMPLETE_OFP_DEMO.md) for detailed documentation.

## 📁 Files

### Demo Agents (No Registration Required)

#### `complete_ofp_demo_simple.py` ⭐ **RECOMMENDED**
Complete demonstration of OFP 1.1 protocol:
- Agents identified only by speakerUri (per spec)
- Floor Manager autonomous decision making
- Priority queue management
- Floor handoff between agents

**Per OFP 1.1**: No agent registration exists. Agents simply send envelopes with their speakerUri.

#### `demo_agents.py`
Basic floor control demonstration:
- Simple HTTP-based demo agents
- No LLM or external API calls
- Fast and free testing

**Note**: These are simulators, not production agents.

### LLM Integration Examples

#### `llm_agent_example.py`
Examples of integrating real LLM providers:
- OpenAI (GPT-4o-mini, GPT-4o)
- Ollama (llama3.1)
- Demonstrates real AI agent conversations

See [../LLM_AGENTS_EXAMPLE.md](../LLM_AGENTS_EXAMPLE.md) for documentation.

#### `quick_llm_test.py`
Quick test to verify OpenAI API key:
```bash
python examples/agents/quick_llm_test.py
```

### Utilities

#### `llm_agent_standalone.py`
Standalone LLM agent (can run independently)

## 🏗️ Architecture (OFP 1.1)

```
┌─────────────────────────────────────┐
│       FLOOR MANAGER                 │
│  (OFP 1.1 Spec Section 2.2)      │
│                                     │
│  • Envelope Processing & Routing    │
│  • Floor Control Logic              │
│  • Priority Queue Management        │
└─────────────────────────────────────┘
              ↕
      OFP 1.1 Envelopes
              ↕
   ┌──────────┐  ┌──────────┐
   │ Agent A  │  │ Agent B  │
   │ (no reg) │  │ (no reg) │
   └──────────┘  └──────────┘
```

**Key Points**:
- ✅ **No Agent Registration**: Per OFP 1.1, agents are identified only by `speakerUri` in envelopes
- ✅ **Floor Manager**: Central component that routes envelopes and manages floor control
- ✅ **Dynamic Discovery**: Agents can use getManifests/publishManifests for dynamic capability discovery (not implemented yet)

## 🎓 OFP 1.1 Key Concepts

### 1. No Central Registry
Per [OFP 1.1 Spec Section 0.5](https://github.com/open-voice-interoperability/openfloor-docs/blob/working_group/specifications/ConversationEnvelope/1.0.1/InteroperableConvEnvSpec.md):
- Agents are identified ONLY by their `speakerUri` in envelopes
- No registration or central registry exists
- Discovery is dynamic via getManifests/publishManifests events

### 2. Floor Manager
Per Spec Section 0.2:
- Central "hub" that coordinates conversation
- Routes envelopes between agents (built-in, not separate component)
- Manages floor control (requestFloor, grantFloor, yieldFloor, revokeFloor)
- Implements minimal floor management behaviors (Spec Section 2.2)

### 3. Convener Agent (Optional)
Per Spec Section 0.4.3:
- "Convener" is an OPTIONAL AGENT that mediates conversations
- Like a "meeting chair"
- NOT the Floor Manager (which is our system component)

## 📚 Usage Examples

### Example 1: Complete OFP Demo

```bash
# Start Floor Manager
docker-compose up -d

# Run complete demo
python examples/agents/complete_ofp_demo_simple.py
```

**Output**: Shows complete floor control flow with priority queue.

### Example 2: LLM Agents

```bash
# Set API key
export OPENAI_API_KEY="sk-..."

# Run LLM example
python examples/agents/llm_agent_example.py
```

**Output**: Real AI agents having a conversation via Floor Manager.

### Example 3: Manual Floor Control

```python
import httpx

# Create agent (no registration needed)
agent_uri = "tag:example.com,2025:my_agent"

# Request floor
async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://localhost:8000/api/v1/floor/request",
        json={
            "conversation_id": "conv_001",
            "speakerUri": agent_uri,
            "priority": 5
        }
    )
    print(response.json())  # {"granted": True, ...}
```

## 🔧 Creating Your Own Agent

### Minimal OFP 1.1 Agent

```python
import httpx

class MinimalOFPAgent:
    def __init__(self, speaker_uri: str):
        # No registration needed per OFP 1.1
        self.speakerUri = speaker_uri
        self.client = httpx.AsyncClient()
    
    async def request_floor(self, conversation_id: str, priority: int = 5):
        """Request floor from Floor Manager"""
        response = await self.client.post(
            "http://localhost:8000/api/v1/floor/request",
            json={
                "conversation_id": conversation_id,
                "speakerUri": self.speakerUri,
                "priority": priority
            }
        )
        return response.json()
    
    async def send_utterance(self, conversation_id: str, text: str):
        """Send utterance to Floor Manager"""
        response = await self.client.post(
            "http://localhost:8000/api/v1/envelopes/utterance",
            json={
                "conversation_id": conversation_id,
                "sender_speakerUri": self.speakerUri,
                "text": text,
                "private": False
            }
        )
        return response.json()
    
    async def yield_floor(self, conversation_id: str):
        """Yield floor back to Floor Manager"""
        response = await self.client.post(
            "http://localhost:8000/api/v1/floor/release",
            json={
                "conversation_id": conversation_id,
                "speakerUri": self.speakerUri
            }
        )
        return response.json()

# Usage
agent = MinimalOFPAgent("tag:example.com,2025:my_agent")
await agent.request_floor("conv_001", priority=5)
await agent.send_utterance("conv_001", "Hello!")
await agent.yield_floor("conv_001")
```

**Key Points**:
- ✅ No registration needed - just use your speakerUri
- ✅ Floor Manager handles all routing and floor control
- ✅ Simple HTTP API

## 🧪 Testing

### Run All Examples

```bash
# Install dependencies
pip install -r requirements.txt

# Run complete demo
python examples/agents/complete_ofp_demo_simple.py

# Run basic demo
python examples/agents/demo_agents.py

# Run LLM example (requires API key)
export OPENAI_API_KEY="sk-..."
python examples/agents/llm_agent_example.py
```

## 📖 Documentation

- **Getting Started**: [../../docs/GETTING_STARTED.md](../../docs/GETTING_STARTED.md)
- **OFP 1.1 Spec Analysis**: [../../docs/OFP_1.0.1_OFFICIAL_SPEC_ANALYSIS.md](../../docs/OFP_1.0.1_OFFICIAL_SPEC_ANALYSIS.md)
- **LLM Integration**: [../../docs/LLM_INTEGRATION.md](../../docs/LLM_INTEGRATION.md)
- **Complete OFP Demo**: [COMPLETE_OFP_DEMO.md](COMPLETE_OFP_DEMO.md)

## 🎯 OFP 1.1 Compliance

These examples demonstrate:

- ✅ **No Registration**: Agents identified only by speakerUri (Spec Section 0.5)
- ✅ **Floor Manager**: Central hub coordinating conversation (Spec Section 0.2)
- ✅ **Minimal Behaviors**: Floor control per Spec Section 2.2
- ✅ **Priority Queue**: Floor requests managed by priority
- ✅ **Envelope Routing**: Built into Floor Manager (not separate)
- ✅ **Floor Events**: requestFloor, grantFloor, yieldFloor, revokeFloor (Spec Sections 1.19-1.22)

## 🔗 References

- [OFP 1.1 Official Specification](https://github.com/open-voice-interoperability/openfloor-docs/blob/working_group/specifications/ConversationEnvelope/1.0.1/InteroperableConvEnvSpec.md)
- [Floor Manager API Documentation](http://localhost:8000/docs)

---

**Ready to build OFP 1.1 compliant agents?** Start with `complete_ofp_demo_simple.py` to see the protocol in action!

