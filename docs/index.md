# Kayori v2 Documentation

Welcome to the Kayori v2 documentation!

## What is Kayori v2?

Kayori v2 is an async, adapter-based AI companion built around LangGraph. It provides a modular runtime for AI agents with:

- **Platform Adapters**: Discord, Telegram, Console, and Webhook support
- **Message Bus**: Decoupled message handling with in-memory or Redis backends
- **Agent Orchestration**: LangGraph ReAct agent with tool integration
- **Flexible Output Routing**: Direct or multi-platform message delivery

## Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/kayori_v2.git
cd kayori_v2

# Install dependencies
uv sync --dev

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run the bot
python examples/main.py
```

## Documentation Sections

- [Getting Started](getting-started.md) - Setup, environment, and running locally
- [Architecture](architecture.md) - Runtime flow, adapters, agent, and output routing

## Getting Help

- [GitHub Issues](https://github.com/yourusername/kayori_v2/issues) - Bug reports and feature requests
- [Discussions](https://github.com/yourusername/kayori_v2/discussions) - Questions and community support
