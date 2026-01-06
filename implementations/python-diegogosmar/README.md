# Python Floor Manager Implementation

**Author**: Diego Gosmar  
**Repository**: https://github.com/diegogosmar/floor  
**Language**: Python 3.11+  
**OFP Version**: 1.0.1  
**License**: MIT

## Overview

A complete Python implementation of the Open Floor Protocol 1.0.1 Floor Manager, providing a full-featured multi-agent conversation management system with floor control, envelope routing, and agent orchestration.

## Key Features

- ✅ **Full OFP 1.0.1 Compliance**
  - Floor Manager as autonomous Convener (state machine)
  - `assignedFloorRoles` and `floorGranted` in conversation object
  - Privacy flag handling (only for utterance events)
  - `acceptInvite` event support

- ✅ **Complete Floor Manager Implementation**
  - Floor control primitives (requestFloor, grantFloor, revokeFloor, yieldFloor)
  - Autonomous decision-making by convener
  - Priority-based floor queue
  - Timeout handling

- ✅ **Envelope Processing**
  - OFP 1.0.1 compliant JSON envelope structure
  - Event routing between agents
  - Support for all OFP event types

- ✅ **REST API**
  - FastAPI-based REST endpoints
  - Interactive Swagger UI documentation
  - Easy integration with existing systems

- ✅ **Agent Support**
  - Agent registry and capability discovery
  - Base agent classes for easy extension
  - LLM agent support (OpenAI, Anthropic, Ollama)
  - Example agents for testing

- ✅ **Orchestration Patterns**
  - Convener-based orchestration
  - Collaborative floor passing
  - Hybrid delegation model

- ✅ **Production Ready**
  - Docker Compose deployment
  - PostgreSQL and Redis support (configured, in-memory for now)
  - Comprehensive test suite
  - Extensive documentation

## Architecture

```
┌─────────────────────────────────────────────┐
│           FLOOR MANAGER (Convener)          │
│  • Floor Control (autonomous state machine) │
│  • Envelope Routing                         │
│  • Agent Registry                           │
└─────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+ (or 3.12 recommended)
- Docker and Docker Compose

### Installation

```bash
# Clone repository
git clone https://github.com/diegogosmar/floor.git
cd floor

# Start services
docker-compose up -d

# Verify
curl http://localhost:8000/health
```

### Test with Demo Agents

```bash
# Install dependencies
pip install httpx

# Run complete OFP flow demo
python examples/agents/complete_ofp_demo.py

# Or run basic demo
python examples/agents/demo_agents.py
```

## Documentation

- **Main Repository**: https://github.com/diegogosmar/floor
- **Quick Start**: https://github.com/diegogosmar/floor#quick-start
- **OFP 1.0.1 Analysis**: https://github.com/diegogosmar/floor/blob/main/docs/OFP_1.0.1_ANALYSIS.md
- **Architecture**: https://github.com/diegogosmar/floor/blob/main/docs/ARCHITECTURE_DETAILED.md
- **API Docs**: http://localhost:8000/docs (when running)

## Technology Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI
- **Database**: PostgreSQL 15 (configured)
- **Cache**: Redis 7 (configured)
- **Testing**: pytest, pytest-asyncio

## OFP 1.0.1 Compliance

This implementation fully complies with OFP 1.0.1 specification:

- ✅ Floor Manager acts as autonomous Convener
- ✅ `assignedFloorRoles` tracks convener role
- ✅ `floorGranted` tracks current floor state
- ✅ Privacy flag only respected for utterance events
- ✅ All OFP 1.0.1 event types supported
- ✅ Conversation envelope structure compliant

## Example Usage

### Request Floor

```bash
curl -X POST http://localhost:8000/api/v1/floor/request \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id": "conv_001",
    "speakerUri": "tag:example.com,2025:agent_1",
    "priority": 5
  }'
```

### Send Envelope

```bash
curl -X POST http://localhost:8000/api/v1/envelopes/send \
  -H "Content-Type: application/json" \
  -d '{
    "envelope": {
      "openFloor": {
        "schema": {"version": "1.0.1"},
        "conversation": {"id": "conv_001"},
        "sender": {"speakerUri": "tag:example.com,2025:agent_1"},
        "events": [{
          "eventType": "utterance",
          "parameters": {
            "dialogEvent": {
              "speakerUri": "tag:example.com,2025:agent_1",
              "features": {
                "text": {
                  "mimeType": "text/plain",
                  "tokens": [{"token": "Hello!"}]
                }
              }
            }
          }
        }]
      }
    }
  }'
```

## License

MIT License - See [LICENSE](https://github.com/diegogosmar/floor/blob/main/LICENSE) file

## Contributing

Contributions welcome! See the main repository for contribution guidelines.

## Links

- **Repository**: https://github.com/diegogosmar/floor
- **OFP Specification**: https://github.com/open-voice-interoperability/openfloor-docs
- **Issues**: https://github.com/diegogosmar/floor/issues

