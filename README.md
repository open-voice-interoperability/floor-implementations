# floor-implementations

This repository contains implementations of the Floor Manager component of the Open Floor Protocol.

## Implementations

### Python Implementation (by Diego Gosmar)

- **Repository**: https://github.com/diegogosmar/floor
- **Language**: Python 3.11+
- **OFP Version**: 1.0.1
- **License**: MIT
- **Features**: 
  - Full Floor Manager with REST API
  - Agent registry and capability discovery
  - LLM agent support (OpenAI, Anthropic, Ollama)
  - Docker Compose deployment
  - Comprehensive test suite
  - Full OFP 1.0.1 compliance

This implementation provides a complete Floor Manager per OFP 1.0.1 specification, with the Floor Manager acting as an autonomous Convener. It includes FastAPI REST endpoints, envelope processing, and support for multiple orchestration patterns.

See [implementation README](implementations/python-diegogosmar/README.md) for details.
