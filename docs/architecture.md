# Architecture

Kayori v2 uses a modular, adapter-based architecture designed for flexibility and extensibility.

## The Big Picture

**Message Flow:**
```
Input → Gateway BUS → Orchestrator → Agent → Output Sink → Response
```

Think of it like this:
1. **Input adapters** listen to platforms (Discord, Telegram, Webhook)
2. **Message Bus** queues incoming messages
3. **Orchestrator** coordinates everything (mood, memory, agent, scheduling)
4. **Agent** generates responses using LangGraph + tools
5. **Output Sink** routes replies back to the right platform

---

## Core Components

### 1. Adapters (The Pluggable Layer)

Adapters let you swap platforms and backends without touching core logic.

**Input Adapters:** Where messages come from
- Discord, Telegram, Webhook, Console

**Output Adapters:** Where responses go
- Discord, Telegram, Webhook (with TTS), Console

**Backend Adapters:** Storage and infrastructure
- **Message Bus:** Redis queue (or in-memory)
- **State Store:** Redis for mood, history, life notes (or in-memory)
- **Episodic Memory:** Redis vector search for long-term facts (or in-memory)
- **Scheduler:** Redis-backed trigger system (or in-memory)

### 2. Orchestrator (The Coordinator)

The `AgentOrchestrator` is the runtime coordinator. It:
- Consumes messages from the bus
- Routes by type: **chat**, **life** (internal reflection), or **compact** (history cleanup)
- Coordinates mood analysis, memory recall, and agent response generation
- Manages conversation threads (per-user/per-channel isolation)
- Handles proactive history compaction after inactivity

### 3. Agent System (The Brain)

**Two agents work together:**

**Chat Agent** (`ReactAgentService`):
- Main conversational agent using LangGraph ReAct pattern
- Has access to tools (Spotify, reminders, search, calendar)
- Generates responses to user messages

**Life Agent** (`LifeAgentService`):
- Internal reflection agent that runs on schedule
- Generates "life notes" from conversations for long-term learning
- Works in the background, not directly visible to users

### 4. Mood Engine (Emotional Intelligence)

Tracks emotional state across **10 dimensions**:
- **7 Fast emotions** (change quickly): Affection, Amused, Curious, Concerned, Disgusted, Embarrassed, Frustrated
- **3 Long emotions** (change slowly): Trust, Attachment, Confidence

**How it works:**
1. LLM analyzes user message and predicts emotion changes
2. Changes propagate through a conflict/reinforcement graph (e.g., Affection boosts Trust, Frustration conflicts with Affection)
3. Emotions naturally drift back to neutral over time

### 5. Episodic Memory (Long-Term Facts)

Stores durable facts about users with:
- Vector embedding-based retrieval (finds relevant memories)
- Importance and confidence scoring
- Automatic cleanup when storage gets too large
- Categories: identity, preference, relationship, schedule, goal, etc.

### 6. Conversation Contraction (History Management)

Prevents context overflow by:
- Triggering when conversation hits 12 messages
- Summarizing older messages into a compact summary
- Extracting important facts to episodic memory
- Keeping the last 4 messages raw for continuity

### 7. Scheduler (Proactive Behavior)

Drives background tasks:
- **Precise triggers:** Fire at exact intervals
- **Fuzzy triggers:** Fire with random delay spread (more natural)
- **Repeating support:** Auto-reschedule recurring tasks
- Used for: LIFE reflections, compaction timers, reminders

### 8. Output Sink (Response Router)

Routes outbound messages:
- **Direct mode:** Reply to same platform (Discord → Discord)
- **Multi mode:** Broadcast to all platforms (for testing/mirroring)
- Isolates failures (one platform failing doesn't break others)

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    PLATFORM LAYER                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Discord  │  │ Telegram │  │ Webhook  │              │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘              │
│       │              │              │                    │
│  ┌────▼──────────────▼──────────────▼─────┐             │
│  │         INPUT ADAPTERS                 │             │
│  └────────────────┬───────────────────────┘             │
└───────────────────┼─────────────────────────────────────┘
                    │ MessageEnvelope
┌───────────────────▼─────────────────────────────────────┐
│                    CORE LAYER                            │
│  ┌──────────────────────────────────────────┐           │
│  │          MESSAGE BUS (Redis)             │           │
│  └────────────────┬─────────────────────────┘           │
│                   │                                     │
│  ┌────────────────▼────────────────────────┐            │
│  │         ORCHESTRATOR                     │            │
│  │  ┌──────────────────────────────────┐   │            │
│  │  │  Mood Engine                     │   │            │
│  │  │  Episodic Memory                 │   │            │
│  │  │  Conversation Contraction        │   │            │
│  │  │  Scheduler                       │   │            │
│  │  └──────────────────────────────────┘   │            │
│  └────────────────┬────────────────────────┘            │
│                   │                                     │
│  ┌────────────────▼────────────────────────┐            │
│  │         AGENT SYSTEM                     │            │
│  │  ┌────────────┐    ┌──────────────┐    │            │
│  │  │ Chat Agent │    │ Life Agent   │    │            │
│  │  │ (ReAct)    │    │ (Reflection) │    │            │
│  │  └────────────┘    └──────────────┘    │            │
│  │         │                               │            │
│  │  ┌──────▼──────────────────────┐       │            │
│  │  │  Tools (Spotify, Search,    │       │            │
│  │  │         Reminder, Calendar) │       │            │
│  │  └─────────────────────────────┘       │            │
│  └────────────────┬────────────────────────┘            │
│                   │                                     │
│  ┌────────────────▼────────────────────────┐            │
│  │         OUTPUT SINK                      │            │
│  └────────────────┬────────────────────────┘            │
└───────────────────┼─────────────────────────────────────┘
                    │ OutboundMessage
┌───────────────────▼─────────────────────────────────────┐
│                   OUTPUT LAYER                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Discord  │  │ Telegram │  │ Webhook  │              │
│  │  Output  │  │  Output  │  │ + TTS    │              │
│  └──────────┘  └──────────┘  └──────────┘              │
└─────────────────────────────────────────────────────────┘
```

---

## Architecture Pros and Cons

### ✅ Strengths

**1. Highly Extensible**
- Adapter pattern makes it trivial to add new platforms
- Want to add Slack? Create input/output adapters, wire them in, done
- Backend adapters let you swap Redis for other storage without touching core logic

**2. Clean Separation of Concerns**
- Each component has one clear responsibility
- Orchestrator coordinates, doesn't implement business logic
- Mood engine is stateless and testable in isolation
- Memory systems are backend-agnostic via protocols

**3. Resilient by Design**
- Async-first with proper error handling everywhere
- Graceful degradation (timeouts, fallbacks, neutral defaults)
- Output sink isolates failures (one platform down ≠ system down)
- Structured logging for debugging

**4. Sophisticated Features**
- Real emotional continuity across conversations
- Long-term memory with semantic search
- Proactive behavior via scheduler
- Automatic history management prevents context overflow

**5. Thread Isolation**
- Per-user/per-channel conversation state
- Multiple users don't interfere with each other
- Thread ID resolution handles complex routing scenarios

### ❌ Limitations

**1. Heavy Redis Dependency**
- All production backends use Redis (bus, state, memory, scheduler)
- In-memory alternatives exist but are commented out in main.py
- Redis becomes a single point of failure
- Requires Redis infrastructure for any serious deployment

**2. Complexity Overhead**
- Many moving parts for a chatbot
- Steep learning curve for contributors
- Multiple async event loops to reason about
- Protocol-based interfaces add indirection

**3. Tight Coupling in Orchestrator**
- `_handle_chat()` orchestrates 8 sequential steps
- Knows about compact trigger policy directly
- Could benefit from more event-driven decomposition

**4. Limited Testing**
- Only `smoke_imports.py` test exists
- Complex mood engine has no unit tests
- Orchestrator coordination logic untested
- Memory compaction edge cases unverified

**5. Resource Intensive**
- Requires Python 3.13+ (strict version lock)
- Multiple LLM calls per turn (chat + mood + compaction + life)
- Vector embeddings add memory/CPU overhead
- Redis VL for vector search needs sufficient RAM

**6. Scheduler Limitations**
- Relative-time only (no absolute wall-clock scheduling)
- No custom callbacks (everything goes through message bus)
- Final behavior depends on orchestrator's source handling
- Limited to interval-based triggers (no cron-like expressions)

---

## When to Use This Architecture

### ✅ Good Fit For:
- Multi-platform AI companions/assistants
- Systems needing emotional continuity
- Applications with long-term memory requirements
- Projects requiring platform flexibility
- Research into AI emotional intelligence

### ❌ Poor Fit For:
- Simple single-platform bots
- Resource-constrained environments
- Projects needing quick time-to-market
- Systems without Redis infrastructure
- Stateless conversational interfaces

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.13 (strict) |
| Agent Framework | LangGraph 1.0+ |
| LLM Abstraction | LangChain |
| LLM Provider | Groq (openai/gpt-oss models) |
| Infrastructure | Redis (state, memory, scheduling, bus) |
| Vector Search | RedisVL |
| Web Framework | FastAPI + Uvicorn |
| Platform SDKs | Discord.py, python-telegram-bot |
| Embeddings | FastEmbed (BAAI/bge-small-en-v1.5) |
| Package Manager | uv |

---

## Key Design Decisions

**Why Redis for Everything?**
- Single infrastructure dependency
- Excellent async support in Python
- Built-in queue operations for message bus
- RedisVL provides vector search without separate database
- Atomic operations prevent race conditions

**Why Dual Agent System?**
- Chat agent focuses on user-facing responses
- Life agent handles background reflection
- Separation prevents internal processing from blocking user interactions
- Different models can be used (120B for chat, 20B for reflection)

**Why Message Bus Architecture?**
- Decouples input from processing
- Enables async event-driven design
- Makes scheduling natural (triggers = messages)
- Allows future parallel processing

**Why Stateless Mood Engine?**
- Thread state belongs in state store, not engine
- Makes testing easier (pass in state, get out state)
- Reusable across threads and scenarios
- Clear boundary between logic and data

---

## Extending the System

### Adding a New Platform

1. Create input adapter implementing `InputAdapter` protocol
2. Create output adapter implementing `OutputAdapter` protocol
3. Publish `MessageEnvelope` to bus from input
4. Wire adapters in `main.py`

### Adding a New Tool

1. Extend `langchain_core.tools.BaseTool`
2. Implement `_arun` async method
3. Add to agent's tool list in `main.py`

### Swapping Backends

1. Implement protocol (e.g., `MessageBus`, `StateStore`)
2. Create new adapter in `src/adapters/`
3. Swap instantiation in `main.py`

---

## File Structure

```
src/
├── adapters/          # Pluggable platform and backend code
│   ├── input/         # Discord, Telegram, Webhook, Console
│   ├── output/        # Discord, Telegram, Webhook, Console
│   ├── runtime/       # Platform lifecycle management
│   ├── bus/           # Message queue implementations
│   ├── state/         # State storage backends
│   ├── memory/        # Episodic memory backends
│   ├── scheduler/     # Scheduler backends
│   └── audio/         # STT (Whisper) and TTS (EdgeTTS)
├── agent/             # LangGraph agent implementations
│   ├── chat/          # Main ReAct conversational agent
│   └── life/          # Internal reflection agent
├── core/              # Core business logic
│   ├── orchestrator.py        # Runtime coordinator
│   ├── mood_engine.py         # Emotion tracking
│   ├── episodic_memory.py     # Long-term fact storage
│   ├── conversation_contraction.py  # History management
│   ├── scheduler.py           # Proactive behavior
│   └── outputsink.py          # Response routing
├── tools/             # Agent tools (Spotify, reminders, etc.)
├── templates/         # Prompt templates
├── shared_types/      # Models, protocols, and types
└── logger/            # Structured logging
```

---

## Next Steps

- Read about individual components in the Core Components section
- Check out [Getting Started](getting-started.md) for setup instructions
- Explore specific component docs for implementation details
