# Changelog

All notable changes to Kayori v2 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial open-source release with restructured package layout
- `src/` package structure for proper Python packaging
- GitHub Actions workflows for CI/CD
- Documentation scaffolding with mkdocs
- Import smoke check for local module resolution
- Pre-commit hooks for code quality
- CONTRIBUTING.md, CODE_OF_CONDUCT.md, and SECURITY.md

### Changed
- Moved all source code to `src/` and properly formatted the codebase

### Added
- Async, adapter-based AI companion architecture
- LangGraph ReAct agent integration
- Platform adapters: Discord, Telegram, Console, Webhook
- Input/Output adapter pattern with message bus
- Agent orchestrator for message handling
- Mood system (foundational)
- Tool implementations: Weather, Reminder, Spotify, Tavily Search
- Audio pipeline with STT/TTS support
- Tool audit logging
- Circuit breaker pattern for external APIs
- In-memory state store and message bus
- Webhook REST API with authentication

### Technical Details
- Python 3.14+
- LangGraph for agent orchestration
- FastAPI for webhook runtime
- discord.py for Discord integration
- python-telegram-bot for Telegram integration

---

For more detailed information, see the [README.md](README.md) and [documentation](docs/).
