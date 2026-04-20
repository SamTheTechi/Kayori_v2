# Kayori v2 Documentation

An intelligent, multi-platform AI companion with emotional awareness and long-term memory.

## What is Kayori?

Kayori is a conversational AI agent that:

- **Converses naturally** across Discord, Telegram and endpoint
- **Remembers** you via vector-based episodic memory with automatic fact extraction and compaction
- **Feels emotionally** real with 10 mood dimensions which builds trust/attachment over time
- **Has her own life** journals thoughts and feelings in the background, shaped by her personality, memories, and your conversations
- **Controls your world** Spotify, reminders, Google Calendar, and web search
- **Acts proactively** with custome scheduled background tasks
- **Supports voice** via Whisper STT and EdgeTTS

## Quick Start

```bash
# Install
uv sync

# Configure
cp example.env .env
# Edit .env with your API keys

# Run
python main.py
```

See [Getting Started](getting-started.md) for detailed setup.

---

## Documentation

### Core Concepts

- **[Architecture](architecture.md)** - System design, components, pros/cons
- **[Agent System](agent.md)** - Chat and Life agents
- **[Mood Engine](mood-engine.md)** - Emotional intelligence
- **[Episodic Memory](episodic-memory.md)** - Long-term fact storage
- **[Scheduler](scheduler.md)** - Proactive behavior
- **[Tools](tools.md)** - Spotify, reminders, search, calendar

### Adapters

- **[Adapter Overview](adapters/overview.md)** - The pluggable architecture
- **[Input Adapters](adapters/input.md)** - Discord, Telegram, Webhook, Console
- **[Output Adapters](adapters/output.md)** - Response routing
- **[Backend Adapters](adapters/backends.md)** - Redis storage and infrastructure

### Reference

- **[Orchestrator](orchestrator.md)** - Runtime coordination
- **[Conversation Contraction](conversation-contraction.md)** - History management
- **[Output Sink](output-sink.md)** - Response routing logic

---

## Key Features

### Emotional Intelligence

Kayori tracks mood across 10 dimensions:
- **Fast emotions**: Affection, Amused, Curious, Concerned, Disgusted, Embarrassed, Frustrated
- **Long emotions**: Trust, Attachment, Confidence

Emotions influence responses and evolve over time.

### Long-Term Memory

- Stores important facts about you
- Finds relevant memories via semantic search
- Automatically extracts facts from conversations
- Compacts old memories to stay efficient

### Proactive Behavior

- Scheduled background tasks
- Self-reflection on conversations
- Automatic history cleanup
- Customizable triggers

---

## Architecture at a Glance

```
 Input -→  Message Bus -→  Orchestrator -→  Agent -→  Output
(Discord)   (Redis)        (Coordinator)    (LLM)  (Discord)
(Telegram)                                 (Tools) (Telegram)
(Webhook)                                           (Webhook)
```

Read the full [Architecture](architecture.md) doc for details.

---

## Tech Stack

- **Python 3.13** with async/await
- **LangGraph** for agent orchestration
- **Groq** for LLM inference
- **FastAPI** for webhook runtime

---

## Getting Help

- **[GitHub Issues](https://github.com/SamTheTechi/kayori_v2/issues)** - Bugs and features
- **[Architecture Doc](architecture.md)** - System design overview
- **[Getting Started](getting-started.md)** - Setup guide
