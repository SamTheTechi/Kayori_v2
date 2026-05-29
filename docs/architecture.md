# Architecture

Kayori v2 uses a modular, adapter-based architecture designed for flexibility and extensibility.

## The Big Picture

**Message Flow:**
```
Input → Gateway BUS → Orchestrator → Specialized Flow → Output Sink → Response
```

Think of it like this:
- **Input adapters** listen to platforms Discord, Telegram or  Webhook
- **Message Bus** decouples inbound events from runtime processing
- **Orchestrator** reads each `MessageEnvelope` and routes it by source/type
- **Specialized Flows** handle chat, life reflection, compaction, and proactive behavior
- **Output Sink** routes outbound replies back to the correct platform(s)

---

## Core Components

### 1. Adapters (The Pluggable Layer)

Adapters isolate platform and backend concerns so the runtime can evolve without rewriting core coordination logic.

**Input Adapters:** Where messages come from
- Discord, Telegram, Webhook, Console

**Output Adapters:** Where responses go
- Discord, Telegram, Webhook (with TTS), Console

**Backend Adapters:** Storage and infrastructure
- **Message Bus:** queue (Redis or in-memory)
- **State Store:** mood, history, life notes (Redis or in-memory)
- **Episodic Memory:** vector search for long-term facts (RedisVL or Pinecone or in-memory)
- **Scheduler:** trigger system (Redis or in-memory)

### 2. Orchestrator (The Coordinator)

The `AgentOrchestrator` is the runtime coordinator. it inspects each `MessageEnvelope` and branches into different flows depending on the envelope source.

Current routing behavior:
- **Chat flow** for normal inbound platform messages
- **Life flow** for internal reflective processing
- **Compaction flow** for history cleanup and memory extraction
- **Proactive flow** for self-initiated outreach

In practice, the orchestrator is responsible for:
- Consuming envelopes from the bus
- Coalescing adjacent user messages when appropriate
- Routing by source/type before any agent work begins
- Coordinating mood analysis, episodic recall, state updates, and output delivery
- Triggering background behaviors such as compaction and proactive messaging


### 3. Agent Flows (The Decision layer)

Kayori no longer behaves like a system with one single agent entrypoint for everything. The runtime which uses multiple specialized flows, coordinated by the orchestrator.

**Chat Flow**
- Handles normal conversational turns from Discord, Telegram, Console, or Webhook
- Loads conversation context, mood state, and episodic memory
- Calls the main chat agent
- Persists the resulting user/assistant turn
- Sends the final outbound response through the output sink

**Life Flow**
- Handles internal reflection events
- Uses the life agent to generate private life notes from compacted context, episodic memory, and life profile state
- Stores notes for later continuity instead of replying directly to the user

**Compaction Flow**
- Handles conversation contraction events
- Summarizes older history into a compact running summary
- Extracts durable facts into episodic memory
- Shrinks the active context window while preserving continuity

**Proactive Flow**
- Handles internally triggered outreach decisions
- Checks recent interaction state and relationship score before sending anything
- Re-enters the chat response path only when proactive messaging is allowed

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
- Triggering when conversation hits 12 messages (can be more or less)
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
│                      PLATFORM LAYER                     │
│    ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│    │ Discord  │  │ Telegram │  │ Webhook  │             │
│    └────┬─────┘  └────┬─────┘  └────┬─────┘             │
│         │             │             │                   │
│    ┌────▼─────────────▼─────────────▼───────┐           │
│    │              INPUT ADAPTERS            │           │
│    └──────────────────┬─────────────────────┘           │
└───────────────────────┼─────────────────────────────────┘
                        │ MessageEnvelope
┌───────────────────────▼─────────────────────────────────┐
│                    CORE LAYER                           │
│  ┌──────────────────────────────────────────┐           │
│  │          MESSAGE BUS (Redis)             │           │
│  └────────────────┬─────────────────────────┘           │
│                   │                                     │
│  ┌────────────────▼──────────────────────────────┐      │
│  │                 ORCHESTRATOR                  │      │
│  │   Routes each MessageEnvelope by source/type  │      │
│  └────────────────┬──────────────────────────────┘      │
│                   │                                     │
│      ┌────────────┼──────────────┬──────────────┐       │
│      │            │              │              │       │
│  ┌───▼────┐  ┌────▼─────┐  ┌─────▼──────┐  ┌────▼─────┐ │
│  │ Chat   │  │ Life     │  │ Compaction │  │ Proactive│ │
│  │ Flow   │  │ Flow     │  │ Flow       │  │ Flow     │ │
│  └───┬────┘  └────┬─────┘  └─────┬──────┘  └────┬─────┘ │
│      │            │              │              │       │
│  ┌───▼───────────────────────────────────────────────┐  │
│  │ Shared Runtime Services                           │  │
│  │ - Mood Engine                                     │  │
│  │ - Episodic Memory                                 │  │
│  │ - Conversation Contraction                        │  │
│  │ - Scheduler                                       │  │
│  └───┬───────────────────────────────────────────────┘  │
│      │                                                  │
│  ┌───▼───────────────────────────────────────────────┐  │
│  │ Agent / Decision Layer                            │  │
│  │ - Chat Agent                                      │  │
│  │ - Life Agent                                      │  │
│  │ - Tools (Spotify, Search, Reminder, Calendar)     │  │
│  └──────────────────┬────────────────────────────────┘  │
│                     │                                   │
│  ┌──────────────────▼────────────────────────┐          │
│  │          OUTPUT SINK                      │          │
│  └──────────────────┬────────────────────────┘          │
└─────────────────────┼───────────────────────────────────┘
                      │ OutboundMessage
┌─────────────────────▼───────────────────────────────────┐
│                    OUTPUT LAYER                         │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│   │ Discord  │  │ Telegram │  │ Webhook  │              │
│   │  Output  │  │  Output  │  │ + TTS    │              │
│   └──────────┘  └──────────┘  └──────────┘              │
└─────────────────────────────────────────────────────────┘
```

---

## Architectural Priorities

The current design favors modularity and coordination over minimalism.

It is built around:
- an orchestrator that routes envelopes into specialized flows
- adapter boundaries for platform and backend integration
- persistent runtime state for continuity across turns
- scheduled internal events that feed back into the same runtime
- layered services instead of a single monolithic agent entrypoint

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.13  |
| Agent Framework | LangGraph 1.0+ |
| LLM Abstraction | LangChain |
| LLM Provider | Groq (for now but could be any) |
| Vector Search | RedisVL/Pinecone/InMemory cosine similarity |
| Web Framework | FastAPI + Uvicorn |
| Platform SDKs | Discord.py, python-telegram-bot |
| Embeddings | FastEmbed (BAAI/bge-small-en-v1.5) |
| Package Manager | uv |

---

## Key Design Decisions

**Envelope-first routing**
- The orchestrator branches on `MessageEnvelope.source` before doing agent work. This ensures the correct separation of concerns for every event type while using the gateway as the only incoming entry point.

**Separate chat and life services**
- Normal conversation and background life reflection are implemented as different services with different graphs. This keeps reflective note generation out of the normal reply path.

**Stateless turns**
- The runtime persists mood, history, life notes, interaction state, and episodic memory between turns. Background compaction and proactive scheduling are built around that persisted state. The major benefit of storing all the state separately is better control and avoiding non-deterministic behavior inside the internal agent graph.

---

## Extending the System

### Adding a New Platform

1. Add a runtime for the platform under `gateway/platforms/<platform>/runtime.py` if the platform needs its own connection lifecycle.
2. Add an input adapter under `gateway/platforms/<platform>/input.py` that converts platform events into `MessageEnvelope` objects and publishes them to the message bus.
3. Add an output adapter under `gateway/platforms/<platform>/output.py` that accepts `OutboundMessage` objects and sends them back to that platform.
4. Register the new input and output adapters in the builder paths in `main.py`.

### Adding a New Tool

1. Create a new tool class under `tools/` by extending `langchain_core.tools.BaseTool`.
2. Implement the tool logic in `_arun`.
3. Pass in any required dependencies through the tool constructor.
4. Add the tool to the chat or life agent wiring in `main.py`, depending on which flow should use it.

### Swapping Backends

1. Implement the relevant protocol from `shared_types/protocol.py`, such as `MessageBus`, `StateStore`, `EpisodicMemoryBackend`, or `SchedulerBackend`.
2. Add the new implementation under the matching backend module in `gateway/`.
3. Replace the default backend wiring in `main.py`.

---

## File Structure

```
agent/             # LangGraph agents and runtime brain
├── chat/          # ReAct chat agent graph and nodes
├── life/          # Internal "life" reflection agent
├── orchestration/ # Orchestrator, mood engine, output sink
├── memory/        # Episodic memory store + conversation contraction
└── prompts/       # Prompt templates
gateway/           # Platform adapters and infrastructure backends
├── platforms/     # discord, telegram, webhook, console (input/output/runtime)
├── bus/           # Message bus (in-memory, redis)
├── state/         # State store (in-memory, redis)
├── memory/        # Episodic memory backends (in-memory, redis, pinecone)
├── scheduler/     # Scheduler backends + service
├── audio/         # Whisper STT + Edge TTS
└── http/          # Dashboard, logs, metrics routes
config/            # Settings, logging, exceptions
shared_types/      # Models, protocols, trigger types, and envelope types
tools/             # Built-in tools (auto-registered)
web/               # Dashboard static assets
```

---

## Next Steps

- Read about individual components in the Core Components section
- Check out [Getting Started](getting-started.md) for setup instructions
- Explore specific component docs for implementation details
