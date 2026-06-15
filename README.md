# floor-implementations

This repository collects and catalogs the main implementations of the **Floor Manager** component of the Open Floor Protocol (OFP).

## About

The Floor Manager is a core component of the Open Floor Protocol specification, responsible for managing floor control primitives (requestFloor, grantFloor, revokeFloor, yieldFloor) and coordinating conversational turns between agents.

This repository serves as a reference collection for different Floor Manager implementations, showcasing various approaches, languages, and architectural patterns used to implement the OFP specification.

## Testing

This section lists testing tools and harnesses maintained in this repository for validating OFP-compatible agents and workflows.

### OFP Test Harness (Desktop GUI)

- **Repository**: implementations/web-floor/harness
- **Language**: Python 3.11+
- **OFP Version**: OpenFloor-compatible event testing tool
- **License**: See repository license files
- **Technology Stack**:
  - Python desktop GUI workflow
  - Configurable direct or gateway transport modes
  - JSON export and charting support for result analysis
- **Features**:
  - GUI-first configuration and execution of OFP event tests
  - Known-agent and custom-URL target selection
  - Utterance-file and agent-file loading support
  - Result filtering, JSON detail views, and summary charts
  - Optional legacy CLI passthrough for automation

This test harness provides an interactive desktop environment for running repeatable OpenFloor event tests against one or more agents. It is designed for quick manual verification, comparison across targets, and exportable result analysis.

See [harness README](implementations/web-floor/harness/README.md) for details.

## Implementations

This section lists the main Floor Manager implementations available in the community. Each implementation includes:

- Full OFP compliance details
- Technology stack and language
- Key features and capabilities
- Quick start instructions
- Links to complete documentation

### Python-FastAPI-Streamlit Implementation (Redis + PostgreSQL Ready)

- **Repository**: https://github.com/diegogosmar/floor
- **Language**: Python 3.11+
- **OFP Version**: 1.0.1
- **License**: MIT
- **Technology Stack**: 
  - FastAPI REST API
  - Streamlit interactive GUI
  - Redis (configured for caching and message queuing)
  - PostgreSQL (configured for persistent storage)
  - Docker Compose deployment
- **Features**: 
  - Full Floor Manager with REST API
  - Interactive web GUI for testing and visualization
  - Agent registry and capability discovery
  - LLM agent support (OpenAI, Anthropic, Ollama)
  - Ready to scale with Redis + PostgreSQL
  - Comprehensive test suite
  - Full OFP 1.0.1 compliance

This implementation provides a complete Floor Manager per OFP 1.0.1 specification, with the Floor Manager acting as an autonomous Convener. It includes FastAPI REST endpoints, Streamlit-based interactive GUI, envelope processing, and support for multiple orchestration patterns. The architecture is designed to scale with Redis for caching/messaging and PostgreSQL for persistent storage.

See [implementation README](implementations/python-diegogosmar/README.md) for details.

### Assistant Client Implementation (Multi-Agent GUI Convener)

- **Repository**: implementations/assistantClient
- **Language**: Python 3.11+
- **OFP Version**: OpenFloor-compatible client implementation
- **License**: See repository license files
- **Technology Stack**:
  - CustomTkinter desktop GUI
  - HTTP event transport via requests
  - Modular Python architecture (`assistantClient.py`, `ui_components.py`, `event_handlers.py`)
- **Features**:
  - Multi-agent invitation and conversation coordination
  - Floor operations (grant/revoke) and turn control
  - Three-phase event processing (broadcast/process/forward)
  - Conversation history and event/diagnostic windows
  - Support for broadcast and targeted messaging

This implementation provides a desktop convener client for coordinating OpenFloor conversations across multiple agents. It focuses on practical floor-control operations, agent lifecycle management, and transparent event handling in a GUI workflow.

See [implementation README](implementations/assistantClient/README.md) for details.

### web-floor Implementation (Browser Client + Flask Gateway)

- **Repository**: implementations/web-floor
- **Language**: JavaScript (client) + Python (Flask gateway)
- **OFP Version**: OpenFloor-compatible web client implementation
- **License**: See repository license files
- **Technology Stack**:
  - Browser-based JavaScript client UI
  - Flask gateway API for proxy transport
  - Vercel-ready deployment configuration
- **Features**:
  - Invite/uninvite and floor grant/revoke controls
  - Broadcast and targeted utterance routing
  - Conversation history and transport envelope logging
  - Local and hosted deployment modes
  - Integrated launcher for desktop OFP test harness (`ofp_test.py`)

This implementation provides a web-based OpenFloor client derived from assistant-client workflows, with a Flask gateway to simplify agent communication from browser contexts. It supports both local development and hosted deployment scenarios.

See [implementation README](implementations/web-floor/README.md) for details.

### OFP Playground Implementation (Model-Agnostic Multi-Provider Sandbox)

- **Repository**: https://github.com/bladeszasza/OFPlayground
- **Language**: Python 3.10+
- **OFP Version**: OpenFloor-compatible multi-agent runtime
- **License**: Apache-2.0
- **Technology Stack**:
  - Async Python runtime with in-process message bus
  - CLI orchestration with optional Gradio web UI
  - Multi-provider LLM support (Anthropic, OpenAI, Google, HuggingFace)
  - Policy-driven floor manager and orchestration modules
- **Features**:
  - OFP-compliant multi-agent conversations with floor control
  - Multiple floor policies (sequential, round robin, moderated, free-for-all, showrunner-driven)
  - Dynamic agent spawning and orchestrator workflows
  - Remote OFP agent integration via HTTP endpoints
  - Rich examples and architecture documentation

This implementation provides a sandbox for exploring OFP turn-taking and orchestration patterns across heterogeneous model providers. It is designed for experimentation with policy-driven floor behavior, autonomous orchestration, and mixed local/remote agent sessions.

See [implementation README](implementations/ofplayground/README.md) for details.

### STOCKOUT Implementation (Crisis War-Room UI + OFP Floor Demo)

- **Repository**: https://github.com/diegogosmar/stockout
- **Language**: Python 3.11+
- **OFP Version**: OpenFloor-compatible floor API integration
- **License**: MIT
- **Technology Stack**:
  - Streamlit user interface
  - Docker Compose services for floor API and inventory mock
  - Optional OpenAI-driven agent workflows
  - Optional MCP demo integration
- **Features**:
  - War-room transcript and floor decision workflows
  - Convener and agent turn coordination against a floor API
  - Inventory and planning interactions for stockout scenarios
  - Optional LLM multi-agent page with editable prompt assets
  - Self-contained local demo stack with verification tooling

This implementation provides a focused demonstration environment for OFP-based decision coordination in a stockout crisis scenario. It combines a Streamlit war-room interface, floor events, and supporting services to showcase practical multi-agent operations.

See [implementation README](implementations/stockout/README.md) for details.

---

## Contributing

To add your Floor Manager implementation to this collection:

1. Create a directory under `implementations/` with a descriptive name (e.g., `implementations/your-language-yourname/`)
2. Add a `README.md` in that directory describing your implementation
3. Update this main `README.md` to include your implementation in the list above
4. Submit a Pull Request

For more details, see the [Open Floor Protocol documentation](https://github.com/open-voice-interoperability/openfloor-docs).

## Resources

- **OFP Specification**: https://github.com/open-voice-interoperability/openfloor-docs
- **Open Voice Interoperability**: https://github.com/open-voice-interoperability
