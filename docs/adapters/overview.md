# Adapters Overview

Kayori's adapter architecture is its most powerful feature. Adapters let you swap platforms and backends without touching core logic.

## The Adapter Pattern

```
┌─────────────────────────────────────────────┐
│              CORE SYSTEM                     │
│   (Orchestrator, Agents, Mood, Memory)      │
│                                              │
│   Depends on PROTOCOLS, not implementations │
└──────────────────┬──────────────────────────┘
                   │
    ┌──────────────┼──────────────┐
    │              │              │
┌───▼───┐    ┌────▼────┐   ┌────▼────┐
│Input  │    │ Output  │   │Backend  │
│Adapters│    │Adapters │   │Adapters │
└───────┘    └─────────┘   └─────────┘
 Discord       Discord       Redis
 Telegram      Telegram      In-Memory
 Webhook       Webhook       Pinecone
 Console       Console
```

**Key Principle:** Core code depends on Python `Protocol` interfaces, not concrete implementations. This means you can swap any adapter without changing core logic.

---

## Adapter Categories

### 1. Input Adapters
**Purpose:** Listen to platforms and publish messages to the bus

**Available:**
- Discord
- Telegram
- Webhook (REST API)
- Console (CLI)

**Protocol:**
```python
class InputAdapter(Protocol):
    name: str
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
```

**How They Work:**
1. Platform receives message
2. Input adapter wraps it in `MessageEnvelope`
3. Envelope published to message bus
4. Orchestrator consumes from bus

---

### 2. Output Adapters
**Purpose:** Deliver responses to platforms

**Available:**
- Discord
- Telegram
- Webhook (with TTS support)
- Console

**Protocol:**
```python
class OutputAdapter(Protocol):
    name: str
    route_source: MessageSource
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def send(self, message: OutboundMessage) -> None: ...
```

**How They Work:**
1. Orchestrator builds `OutboundMessage`
2. Output sink selects target adapters
3. Adapter delivers to platform
4. Failures logged, don't crash system

---

### 3. Runtime Adapters
**Purpose:** Manage platform lifecycle

**Available:**
- Discord Runtime
- Telegram Runtime
- Webhook Runtime (FastAPI server)

**What They Do:**
- Handle platform-specific initialization
- Manage connections (bot login, HTTP server)
- Provide start/stop lifecycle
- Input/output adapters depend on runtimes

---

### 4. Backend Adapters
**Purpose:** Infrastructure implementations

**Categories:**

#### Message Bus
- **RedisMessageBus**: Persistent queue with LPUSH/BRPOP
- **InMemoryMessageBus**: Volatile queue (commented out)

#### State Store
- **RedisStateStore**: Mood, history, life notes in Redis
- **InMemoryStateStore**: Volatile dict (commented out)

#### Episodic Memory
- **RedisEpisodicMemory**: Vector search with RedisVL
- **InMemoryEpisodicMemory**: Local vector DB (commented out)

#### Scheduler
- **RedisSchedulerBackend**: Persistent trigger storage
- **InMemorySchedulerBackend**: Volatile triggers (commented out)

---

## How Adapters Connect

### Example: Discord Message Flow

```
1. Discord Runtime (bot.login())
   ↓
2. DiscordInputAdapter (on_message event)
   ↓ builds MessageEnvelope
3. RedisMessageBus (lpush)
   ↓
4. Orchestrator (brpop)
   ↓ processes message
5. OutputSink selects DiscordOutputAdapter
   ↓
6. DiscordOutputAdapter (channel.send())
   ↓
7. Discord Runtime (HTTP API)
```

### Example: Adding Slack

```python
# 1. Create runtime
class SlackRuntime:
    def __init__(self, token: str): ...
    async def start(self): ...
    async def stop(self): ...

# 2. Create input adapter
class SlackInputAdapter:
    def __init__(self, runtime, bus): ...
    async def start(self): ...  # Listen to Slack
    async def stop(self): ...

# 3. Create output adapter
class SlackOutputAdapter:
    def __init__(self, runtime, channel_id): ...
    async def send(self, message): ...  # Send to Slack

# 4. Wire in main.py
slack_runtime = SlackRuntime(token=slack_token)
inputs.append(SlackInputAdapter(runtime=slack_runtime, bus=bus))
outputs.append(SlackOutputAdapter(runtime=slack_runtime))
```

**That's it.** Core orchestrator doesn't care it's Slack.

---

## Adapter Pros and Cons

### ✅ Strengths

**Platform Agnostic**
- Core logic never changes when adding platforms
- Test new platforms without touching agents
- Easy to support new messaging apps

**Backend Flexibility**
- Swap Redis for PostgreSQL if needed
- Try different vector databases
- No core code changes required

**Testability**
- Mock protocols for unit tests
- Test core logic with in-memory adapters
- Isolate platform-specific bugs

**Deployment Options**
- Run with Discord only, or all platforms
- Use Redis in production, in-memory for dev
- Enable/disable features via configuration

**Failure Isolation**
- One adapter failing doesn't crash others
- Output sink catches per-adapter errors
- Structured logging identifies culprit

### ❌ Limitations

**Protocol Complexity**
- Python protocols less explicit than interfaces
- Easy to miss protocol requirements
- Runtime errors if protocol not fully implemented

**Adapter Proliferation**
- Many similar files (discord_input, telegram_input, etc.)
- Shared logic duplicated across adapters
- Hard to extract common patterns

**Runtime Dependencies**
- Each adapter pulls in platform SDK
- Discord.py, telegram-bot, FastAPI all loaded
- Larger Docker image, more vulnerabilities

**Configuration Overhead**
- Many env vars to manage
- Easy to misconfigure adapter wiring
- No validation of adapter compatibility

**In-Memory Adapters Unused**
- Commented out in main.py
- May drift out of sync with protocols
- Redis effectively required for production

---

## Creating Custom Adapters

### Step 1: Implement Protocol

```python
from src.shared_types.protocol import InputAdapter, MessageBus
from src.shared_types.models import MessageEnvelope, MessageSource

class MyCustomInput(InputAdapter):
    name = "my_custom"
    
    def __init__(self, bus: MessageBus):
        self.bus = bus
    
    async def start(self):
        # Start listening to your platform
        pass
    
    async def stop(self):
        # Clean up connections
        pass
```

### Step 2: Publish to Bus

```python
envelope = MessageEnvelope(
    source=MessageSource.WEBHOOK,  # or custom enum
    content="User message text",
    author_id="user123",
    channel_id="channel456",
    target_user_id="bot789"
)
await self.bus.publish(envelope)
```

### Step 3: Wire in main.py

```python
from src.adapters.input.my_custom import MyCustomInput

inputs.append(MyCustomInput(bus=bus))
```

---

## Current Production Setup

From `main.py`:

```python
enabled_inputs = ["discord", "webhook"]
enabled_outputs = ["discord", "webhook"]

# All backends use Redis
bus = RedisMessageBus(async_redis)
state = RedisStateStore(async_redis)
memory_backend = RedisEpisodicMemory(redis_client=sync_redis)
scheduler_backend = RedisSchedulerBackend(redis_client=async_redis)
```

**Infrastructure Required:**
- Redis server (single instance)
- Discord bot token
- Webhook server (port 8080)

---

## Adapter Directory Structure

```
src/adapters/
├── input/
│   ├── discord_input.py
│   ├── telegram_input.py
│   ├── webhook_input.py
│   └── console_input.py
├── output/
│   ├── discord_output.py
│   ├── telegram_output.py
│   ├── webhook_output.py
│   └── console_output.py
├── runtime/
│   ├── discord_runtime.py
│   ├── telegram_runtime.py
│   └── webhook_runtime.py
├── bus/
│   ├── redis_bus.py
│   └── in_memory.py (commented out)
├── state/
│   ├── redis.py
│   └── in_memory.py (commented out)
├── memory/
│   ├── redis.py
│   └── in_memory.py (commented out)
├── scheduler/
│   ├── redis.py
│   └── in_memory.py (commented out)
├── audio/
│   ├── stt.py (Whisper)
│   └── tts.py (EdgeTTS)
└── http/
    ├── dashboard.py
    ├── logs.py
    ├── metrics.py
    └── ping.py
```

---

## Key Takeaways

1. **Protocols over implementations**: Core depends on interfaces
2. **Swap anything**: Platforms, backends, storage all pluggable
3. **Redis is king**: Production uses Redis for everything
4. **Easy to extend**: New platform = 3 files (runtime, input, output)
5. **Failure isolation**: Adapters fail independently

---

## Related

- [Input Adapters](input.md) - Detailed input adapter docs
- [Output Adapters](output.md) - Detailed output adapter docs
- [Backend Adapters](backends.md) - Storage and infrastructure
- [Architecture](../architecture.md) - Overall system design
