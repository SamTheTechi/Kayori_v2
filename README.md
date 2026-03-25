# Kayori v2

Kayori v2 is an async, adapter-based AI companion built around LangGraph, platform runtimes, and an orchestrated message pipeline.

## What Kayori Does

Kayori is an intelligent conversational agent that connects to multiple platforms (Discord, Telegram, Webhook) and provides:

- **Natural Conversations** - ReAct-based reasoning with context-aware responses using LangGraph
- **Tool Execution** - Real-world actions like weather lookup, Spotify control, reminders, and web search
- **Emotional Intelligence** - Mood analysis across 10 bounded emotion dimensions
- **Memory** - Short-term conversation history plus long-term episodic memory via pluggable backends
- **Proactive Behavior** - Scheduler-driven actions, inactivity-based history compaction, and internal runtime events
- **Audio Support** - Full speech-to-text (Whisper) and text-to-speech (EdgeTTS) pipeline

Think of it as a personal AI assistant that lives in your chat platforms, remembers conversations, understands emotions, and can take actions on your behalf.

## Architecture Overview

![Architecture Flow](docs/assets/flow.webp)

**Message Flow:**
```
Input → Gateway BUS → Orchestrator → Agent → Output Sink → Response
```

**Core Components:**
- **Gateway BUS** - Central message bus decoupling input from processing
- **Orchestrator** - Routes inbound sources and coordinates the runtime turn flow
- **Agent** - LangGraph ReAct agent with tool access
- **Output Sink** - Routes responses (direct or multi-platform)
- **Scheduler** - Publishes delayed and recurring events into the bus

## Features

- **Multi-Platform**: Discord, Telegram, Webhook runtimes
- **Audio Pipeline**: Whisper STT + EdgeTTS
- **Memory Systems**: Short-term state + Episodic memory with in-memory, Redis, and Pinecone backends
- **Mood Engine**: Fast/long emotion model with classifier-driven deltas
- **Tools**: Reminder, Spotify, Tavily Search, calendar integrations
- **Scheduler**: Precise/fuzzy triggers, repeating tasks, and inactivity-based compaction timers

## Quick Start

**Prerequisites:** Python `>=3.13,<3.14` and API keys for the services you enable

**Environment (.env):**
```env
API_KEY=your_groq_api_key
DISCORD_BOT_TOKEN=your_discord_token
DISCORD_USER_ID=your_user_id
TELEGRAM_BOT_TOKEN=your_telegram_token
```

**Install:**
```bash
uv sync
```

**Run:**
```bash
python main.py
```

## Core Runtime Docs

- [Scheduler](docs/scheduler.md)
- [Mood Engine](docs/mood-engine.md)
- [Orchestrator](docs/orchestrator.md)
- [Episodic Memory](docs/episodic-memory.md)
- [Conversation Contraction](docs/conversation-contraction.md)
- [Output Sink](docs/output-sink.md)

## Project Structure

```
src/
├── adapters/     # Input/output, bus, memory, state, scheduler backends
├── agent/        # LangGraph-based agent service and nodes
├── core/         # Orchestrator, mood, scheduler, episodic memory, contraction
├── templates/    # Prompt templates used by core services
├── tools/        # Built-in tools
└── shared_types/ # Models, protocols, trigger types, and envelope types
```

## License

MIT. See `LICENSE`.
