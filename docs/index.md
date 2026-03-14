# Kayori v2 Documentation

Welcome to the Kayori v2 documentation!

## What is Kayori v2?

Kayori v2 is an intelligent conversational AI agent that connects to Discord, Telegram, and webhooks. It provides:

- **Natural Conversations** - ReAct-based reasoning with context-aware responses
- **Tool Execution** - Weather lookup, Spotify control, reminders, web search, and MCP tools
- **Emotional Intelligence** - Mood analysis across 28 emotions adapting to user sentiment
- **Memory Systems** - Conversation history + long-term episodic memory (Pinecone/Neo4j)
- **Proactive Behavior** - Scheduler-driven curiosity, reminders, and mood-triggered actions
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

## Architecture Overview

![Architecture Flow](../flow.png)

**Message Flow:** `Input → Gateway BUS → Orchestrator → Agent → Output Sink → Response`

## Getting Help

- [GitHub Issues](https://github.com/yourusername/kayori_v2/issues) - Bug reports and feature requests
- [Discussions](https://github.com/yourusername/kayori_v2/discussions) - Questions and community support
