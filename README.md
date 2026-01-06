# floor-implementations

This repository collects and catalogs the main implementations of the **Floor Manager** component of the Open Floor Protocol (OFP).

## About

The Floor Manager is a core component of the Open Floor Protocol specification, responsible for managing floor control primitives (requestFloor, grantFloor, revokeFloor, yieldFloor) and coordinating conversational turns between agents.

This repository serves as a reference collection for different Floor Manager implementations, showcasing various approaches, languages, and architectural patterns used to implement the OFP specification.

## Implementations

This section lists the main Floor Manager implementations available in the community. Each implementation includes:

- Full OFP compliance details
- Technology stack and language
- Key features and capabilities
- Quick start instructions
- Links to complete documentation

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
