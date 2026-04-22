# Complete OFP Demo - Full Protocol Flow

This example demonstrates the **complete Open Floor Protocol flow** including:

1. ✅ Agent registration with manifests
2. ✅ `getManifests` - Capability discovery
3. ✅ `requestFloor` - Floor access request with priority
4. ✅ `grantFloor` - Convener grants floor by priority
5. ✅ Agent utterances
6. ✅ `yieldFloor` - Floor release and handoff

## Prerequisites

**Floor Manager must be running:**

```bash
# Start Floor Manager and services
docker-compose up -d

# Wait for services to be ready
sleep 5

# Verify it's running
curl http://localhost:8000/health
```

## Run the Demo

```bash
python examples/agents/complete_ofp_demo.py
```

## What You'll See

### Step 1: Agent Registration
```
📝 Registering Coordinator Agent...
   ✅ Coordinator Agent registered successfully
   📋 Manifest: {...capabilities, version, etc...}
```

All agents register with the Floor Manager, providing their:
- `speakerUri` - Unique agent identifier
- `agent_name` - Human-readable name
- `capabilities` - What the agent can do (text_generation, data_analysis, etc.)
- `agent_version` - Agent version number

### Step 2: Manifest Discovery (getManifests)
```
📋 GETTING ALL AGENT MANIFESTS (Capability Discovery)
✅ Found 3 registered agents:
   🤖 Agent: Coordinator Agent
      URI: tag:demo.com,2025:coordinator
      Capabilities: text_generation, orchestration
```

This demonstrates how agents can **discover each other's capabilities** using the `getManifests` API endpoint.

### Step 3: Floor Requests (Priority Queue)
```
🙋 Assistant Agent requesting floor (priority: 5)...
   ⏳ Assistant Agent queued for floor

🙋 Data Analyst Agent requesting floor (priority: 7)...
   ⏳ Data Analyst Agent queued for floor

🙋 Coordinator Agent requesting floor (priority: 10)...
   ✅ Floor GRANTED to Coordinator Agent
```

Even though agents request in order (5, 7, 10), the **Convener grants floor by priority**: 10 first, then 7, then 5.

### Step 4: Floor Holder Check
```
🎤 Current floor holder: Coordinator Agent
   URI: tag:demo.com,2025:coordinator
```

Any agent can check who currently holds the floor.

### Step 5: Agent Speaks (Has Floor)
```
💬 Coordinator Agent: 'Welcome everyone! I'll coordinate this session.'
```

Only the agent with floor can send utterances.

### Step 6: Yield Floor
```
👋 Coordinator Agent yielding floor...
   ✅ Floor released by Coordinator Agent
```

When done, the agent yields the floor.

### Step 7: Next Agent Gets Floor (By Priority)
```
🎤 Current floor holder: Data Analyst Agent
   Priority system working! Analyst (priority 7) got floor before Assistant (priority 5)
```

The Convener automatically grants floor to the next highest priority agent in the queue.

### Step 8-11: Process Repeats
The pattern continues: speak → yield → next agent gets floor.

## Understanding the Flow

```
┌─────────────────────────────────────────────────────────┐
│                   FLOOR MANAGER (CONVENER)              │
│                  Autonomous State Machine                │
└─────────────────────────────────────────────────────────┘
           ↑                    ↓
      REGISTER              GRANT FLOOR
    (with manifest)         (by priority)
           ↑                    ↓
┌──────────┴────────────────────┴──────────────────────┐
│                                                       │
│  Agent 1          Agent 2          Agent 3           │
│  (priority 10)    (priority 7)     (priority 5)      │
│                                                       │
│  1. Register      1. Register      1. Register       │
│  2. Request       2. Request       2. Request        │
│     Floor            Floor             Floor          │
│  3. ✅ GRANTED    3. ⏳ Queued      3. ⏳ Queued     │
│  4. Speak         4. Wait           4. Wait          │
│  5. Yield         5. ✅ GRANTED    5. ⏳ Queued     │
│  6. Done          6. Speak          6. ✅ GRANTED   │
│                   7. Yield          7. Speak         │
│                   8. Done           8. Yield         │
│                                     9. Done          │
└───────────────────────────────────────────────────────┘
```

## Key OFP Concepts Demonstrated

### 1. Manifest Registration
```python
{
  "speakerUri": "tag:demo.com,2025:coordinator",
  "agent_name": "Coordinator Agent",
  "capabilities": ["text_generation", "orchestration"],
  "agent_version": "1.0.0"
}
```

### 2. Capability Discovery (getManifests)
```bash
GET /api/v1/agents/
```
Returns all registered agents with their capabilities.

### 3. Floor Control Primitives

| Primitive | Who Calls | Purpose |
|-----------|-----------|---------|
| `requestFloor` | Agent | Request floor access with priority |
| `grantFloor` | Convener | Grant floor to agent (automatic) |
| `yieldFloor` | Agent | Release floor when done |
| `revokeFloor` | Convener | Forcibly take back floor (timeout) |

### 4. Priority Queue
- Agents request with priority (1-10, 10 = highest)
- Convener maintains priority queue
- Floor granted to highest priority first
- FIFO within same priority

### 5. Autonomous Convener
The Floor Manager acts as an **autonomous Convener**:
- No manual intervention needed
- Automatically manages queue
- Grants/revokes floor as needed
- Enforces OFP rules

## Compare with Other Demos

| Demo | Purpose | Floor Manager |
|------|---------|---------------|
| `demo_agents.py` | Floor control basics | ❌ Simulated |
| `llm_agent_example.py` | LLM integration | ❌ Not used |
| **`complete_ofp_demo.py`** | **Full OFP flow** | **✅ Real API** |

## Next Steps

1. **Modify priorities** - Change agent priorities and see order change
2. **Add more agents** - Register 5-10 agents with different capabilities
3. **Integrate LLM** - Combine with `LLMAgent` for AI-powered floor control
4. **Monitor logs** - Watch Floor Manager logs for detailed flow

## Troubleshooting

### Error: "Floor Manager is NOT running"
```bash
# Start services
docker-compose up -d

# Check status
docker-compose ps
```

### Error: Connection refused
```bash
# Check if port 8000 is accessible
curl http://localhost:8000/health

# Check logs
docker-compose logs api
```

## References

- **OFP Specification**: See `docs/OFP_AGENT_INTEGRATION.md`
- **Floor Manager API**: http://localhost:8000/docs (Swagger UI)
- **Architecture**: `docs/ARCHITECTURE_DETAILED.md`






