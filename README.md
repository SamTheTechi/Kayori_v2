# Kayori v2

Kayori v2 is an async, adapter-based AI companion built around LangGraph, platform runtimes, and an orchestrated message pipeline.

## What Kayori Does

Kayori is an intelligent conversational agent that connects to multiple platforms (Discord, Telegram, Webhook) and provides:

- **Natural Conversations** - ReAct-based reasoning with context-aware responses using LangGraph
- **Tool Execution** - Real-world actions like weather lookup, Spotify control, reminders, and web search
- **Emotional Intelligence** - Mood analysis across 28 emotions that adapts responses based on user sentiment
- **Memory** - Short-term conversation history plus long-term episodic memory via vector databases
- **Proactive Behavior** - Scheduler-driven actions including curiosity-based engagement and mood-triggered responses
- **Audio Support** - Full speech-to-text (Whisper) and text-to-speech (EdgeTTS) pipeline

Think of it as a personal AI assistant that lives in your chat platforms, remembers conversations, understands emotions, and can take actions on your behalf.

## Architecture Overview

![Architecture Flow](flow.png)

**Message Flow:**
```
Input → Gateway BUS → Orchestrator → Agent → Output Sink → Response
```

**Core Components:**
- **Gateway BUS** - Central message bus decoupling input from processing
- **Orchestrator** - Manages state and agent execution
- **Agent** - LangGraph ReAct agent with tool access
- **Output Sink** - Routes responses (direct or multi-platform)
- **Scheduler** - Drives proactive behaviors

## Features

- **Multi-Platform**: Discord, Telegram, Webhook runtimes
- **Audio Pipeline**: Whisper STT + EdgeTTS
- **Memory Systems**: Short-term, Episodic (Pinecone), Graph (Neo4j)
- **Mood Engine**: 28 emotion dimensions with dynamic analysis
- **Tools**: Weather, Reminder, Spotify, Tavily Search + MCP tools
- **Scheduler**: Fuzzy/precise scheduling, curiosity triggers, mood thresholds

## Quick Start

**Prerequisites:** Python 3.14+, API keys for services you enable

**Environment (.env):**
```env
API_KEY=your_groq_api_key
DISCORD_BOT_TOKEN=your_discord_token
DISCORD_USER_ID=your_user_id
```

**Install:**
```bash
uv sync  # or: pip install .
```

**Run:**
```bash
python examples/main.py
```

## Project Structure

```
src/
├── adapters/    # Input/Output, Bus, Memory, State, Scheduler
├── agent/       # ReAct agent service
├── core/        # Orchestrator, OutputSink, MoodEngine, Scheduler
├── tools/       # Built-in tools
├── mcp/         # MCP tool integrations
└── shared_types/# Models and protocols
```

## License

MIT. See `LICENSE`.
