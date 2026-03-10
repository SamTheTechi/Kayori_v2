# Architecture

Kayori v2 uses a modular, adapter-based architecture for flexibility and extensibility.

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      Platform Adapters                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐         │
│  │ Discord  │  │ Telegram │  │ Console  │  │ Webhook  │         │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘         │
└───────┼─────────────┼─────────────┼─────────────┼───────────────┘
        │             │             │             │
        └─────────────┴──────┬──────┴─────────────┘
                             │
                    ┌────────▼────────┐
                    │  Message Bus    │
                    │  (In-Mem/Redis) │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Orchestrator   │
                    │  - Consume msg  │
                    │  - Load state   │
                    │  - Call agent   │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  ReAct Agent    │
                    │  (LangGraph)    │
                    │  - Tools        │
                    │  - Memory       │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Output Sink    │
                    │  (Direct/Multi) │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
  ┌─────▼─────┐       ┌──────▼──────┐      ┌──────▼──────┐
  │  Discord  │       │   Telegram  │      │   Webhook   │
  │  Output   │       │   Output    │      │   Output    │
  └───────────┘       └─────────────┘      └─────────────┘
```

## Components

### Adapters

Adapters normalize external platform messages into `MessageEnvelope` objects.

**Input Adapters:**
- `DiscordInputAdapter` - Discord message ingestion
- `TelegramInputAdapter` - Telegram message ingestion
- `ConsoleInputGateway` - Console/CLI input
- `WebhookInputAdapter` - REST/webhook input with STT support

**Output Adapters:**
- `DiscordOutputAdapter` - Discord message delivery
- `TelegramOutputAdapter` - Telegram message delivery
- `ConsoleOutputAdapter` - Console output
- `WebhookOutputAdapter` - Webhook delivery with TTS support

### Message Bus

Decouples input from processing:

- `InMemoryMessageBus` - Default, in-memory queue
- `RedisMessageBus` - Distributed, persistent queue (available but not default)

### Agent Orchestrator

The `AgentOrchestrator` manages the message processing loop:

1. Consumes messages from the bus
2. Loads mood state from state store
3. Calls the ReAct agent
4. Builds outbound messages
5. Sends to output sink

### ReAct Agent

Built with LangGraph, the agent:

- Maintains per-thread conversation history
- Executes tools (Weather, Reminder, Spotify, Search)
- Returns text responses
- Logs tool calls for auditing

### Output Sink

Routes outbound messages:

- **Direct mode**: Reply to the same platform the message came from
- **Multi mode**: Broadcast to all configured outputs

### State Store

Manages application state:

- `InMemoryStateStore` - Default, volatile storage
- `RedisStateStore` - Persistent storage (available but not default)

Stores:
- Mood state (emotions)
- Location data (live/pinned)

## Message Flow

1. **Ingestion**: Platform adapter receives message → creates `MessageEnvelope`
2. **Publishing**: Envelope published to message bus
3. **Consumption**: Orchestrator consumes from bus
4. **Processing**: Agent generates response
5. **Routing**: Output sink delivers to appropriate adapter(s)

## Key Design Decisions

### Why Adapters?

- Easily Swap platforms without changing core logic 
- Add new platforms easily

### Why Message Bus?

- Decouples input from processing
- Remove command drop

### Why LangGraph?

- Built-in state management 
- Tool execution orchestration

## Extending Kayori

### Adding a New Input Adapter

1. Create a class implementing `InputAdapter` protocol
2. Publish `MessageEnvelope` to the bus
3. Register in `main.py`

### Adding a New Tool

1. Extend `langchain_core.tools.BaseTool`
2. Implement `_arun` method
3. Add to agent's tool list

### Custom Output Routing

Modify `OutputSink._select_outputs()` for custom routing logic.
