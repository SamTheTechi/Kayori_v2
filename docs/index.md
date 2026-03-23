# Kayori v2 Documentation

Welcome to the Kayori v2 documentation!

## What is Kayori v2?

Kayori v2 is an intelligent conversational AI agent that connects to Discord, Telegram, and webhooks. It provides:

- **Natural Conversations** - ReAct-based reasoning with context-aware responses
- **Tool Execution** - Weather lookup, Spotify control, reminders, web search, and MCP tools
- **Emotional Intelligence** - Mood analysis across fast and long-term emotion layers
- **Memory Systems** - Conversation history + long-term episodic memory (Pinecone/Neo4j)
- **Proactive Behavior** - Scheduler-driven precise, fuzzy, and life-style triggers
- **Audio Support** - Speech-to-text (Whisper) and text-to-speech (EdgeTTS)

## Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/kayori_v2.git
cd kayori_v2

# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run the bot
python examples/main.py
```

## Documentation Sections

- [Getting Started](getting-started.md) - Setup, environment, and running locally
- [Architecture](architecture.md) - System design, components, and message flow
- [Scheduler](scheduler.md) - Trigger model, scheduling behavior, tradeoffs, and examples
- [Mood Engine](mood-engine.md) - Emotional state model, update rules, and design reasoning

## Architecture Overview

![Architecture Flow](../flow.png)

**Message Flow:** `Input → Gateway BUS → Orchestrator → Agent → Output Sink → Response`

## Getting Help

- [GitHub Issues](https://github.com/yourusername/kayori_v2/issues) - Bug reports and feature requests
- [Discussions](https://github.com/yourusername/kayori_v2/discussions) - Questions and community support
