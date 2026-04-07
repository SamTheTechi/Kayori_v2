# Input Adapters

Input adapters listen to external platforms and publish messages to Kayori's message bus.

## Available Input Adapters

| Adapter | Platform | Use Case |
|---------|----------|----------|
| DiscordInputAdapter | Discord | Chat bots in Discord servers |
| TelegramInputAdapter | Telegram | Chat bots in Telegram groups/DMs |
| WebhookInputAdapter | HTTP REST | Custom integrations, voice (STT) |
| ConsoleInputGateway | CLI | Testing, local development |

---

## How Input Adapters Work

### General Flow

```
Platform Event → Input Adapter → MessageEnvelope → Message Bus → Orchestrator
```

### MessageEnvelope Structure

Every input adapter creates a `MessageEnvelope`:

```python
MessageEnvelope(
    source=MessageSource.DISCORD,     # Where message came from
    content="Hello bot!",              # Actual text content
    author_id="user123",               # Who sent it
    channel_id="channel456",           # Which channel/chat
    target_user_id="bot789",           # Who it's for (optional)
    metadata={...}                     # Extra platform-specific data
)
```

---

## DiscordInputAdapter

### What It Does

Listens to Discord messages and publishes them to the bus.

### Setup

```python
discord_runtime = DiscordRuntime(token=discord_token)
discord_input = DiscordInputAdapter(
    runtime=discord_runtime,
    bus=bus
)
```

### Features

- Listens to Discord message events
- Filters by user/channel (configurable)
- Handles Discord-specific metadata
- Integrates with Discord runtime lifecycle

### Pros
✅ Native Discord integration  
✅ Rich metadata (user roles, channels)  
✅ Supports attachments, embeds  

### Cons
❌ Requires Discord bot token  
❌ Message Content intent needed  
❌ Discord.py dependency  

---

## TelegramInputAdapter

### What It Does

Listens to Telegram messages and publishes them to the bus.

### Setup

```python
telegram_runtime = TelegramRuntime(token=telegram_token)
telegram_input = TelegramInputAdapter(
    runtime=telegram_runtime,
    bus=bus,
    allowed_chat_ids=None  # None = all chats
)
```

### Features

- Listens to Telegram message updates
- Optional chat ID filtering
- Handles Telegram-specific metadata
- Supports groups and direct messages

### Pros
✅ Native Telegram integration  
✅ Works in groups and DMs  
✅ Supports Telegram-specific features  

### Cons
❌ Requires Telegram bot token  
❌ Privacy mode limitations  
❌ python-telegram-bot dependency  

---

## WebhookInputAdapter

### What It Does

Exposes HTTP endpoints for custom integrations. Includes speech-to-text support.

### Setup

```python
webhook_runtime = WebhookRuntime(
    host="0.0.0.0",
    port=8080,
    bearer_token="123"
)
webhook_input = WebhookInputAdapter(
    runtime=webhook_runtime,
    bus=bus,
    stt=WhisperSttAdapter(api_key=groq_api_key)
)
```

### Features

- REST API endpoint (`POST /webhook`)
- Bearer token authentication
- Audio file transcription via Whisper STT
- Custom route registration
- Integrates with FastAPI server

### Endpoints

- `POST /webhook` - Receive messages
- Audio files automatically transcribed
- JSON payload expected

### Pros
✅ Platform agnostic  
✅ Custom integrations possible  
✅ Audio/voice support  
✅ Easy to test with curl/Postman  

### Cons
❌ Requires HTTP server setup  
❌ Authentication is simple bearer token  
❌ No built-in rate limiting  

---

## ConsoleInputGateway

### What It Does

Reads from stdin for local testing and development.

### Setup

```python
console_input = ConsoleInputGateway(bus=bus)
```

### Features

- Simple CLI input
- No external dependencies
- Great for testing core logic
- Blocks on stdin

### Pros
✅ Zero configuration  
✅ No API keys needed  
✅ Perfect for development  
✅ Instant feedback loop  

### Cons
❌ Not for production  
❌ Single user only  
❌ No platform features  

---

## Creating a Custom Input Adapter

### Step 1: Implement Protocol

```python
from src.shared_types.protocol import InputAdapter, MessageBus
from src.shared_types.models import MessageEnvelope, MessageSource

class MyPlatformInput(InputAdapter):
    name = "my_platform"
    
    def __init__(self, runtime, bus: MessageBus):
        self.runtime = runtime
        self.bus = bus
        self._running = False
    
    async def start(self):
        self._running = True
        # Start listening to platform
        await self._listen()
    
    async def stop(self):
        self._running = False
    
    async def _listen(self):
        while self._running:
            message = await self._receive_message()
            envelope = MessageEnvelope(
                source=MessageSource.WEBHOOK,  # or custom
                content=message.text,
                author_id=message.user_id,
                channel_id=message.channel_id,
                metadata={"platform": "my_platform"}
            )
            await self.bus.publish(envelope)
```

### Step 2: Wire in main.py

```python
from src.adapters.input.my_platform import MyPlatformInput

inputs.append(MyPlatformInput(runtime=my_runtime, bus=bus))
```

---

## Input Adapter Pros and Cons (Overall)

### ✅ Strengths

**Platform Independence**
- Core logic never knows about Discord/Telegram
- Easy to add new platforms
- Test with console input

**Uniform Message Format**
- All platforms become `MessageEnvelope`
- Orchestrator handles one message type
- Metadata preserved but not required

**Lifecycle Management**
- Clean start/stop methods
- Runtime handles platform initialization
- Graceful shutdown support

**Async-First Design**
- Non-blocking message publishing
- Multiple inputs run concurrently
- No platform blocks others

### ❌ Limitations

**Platform SDK Dependencies**
- Each adapter pulls in heavy SDKs
- Larger Docker image
- More security surface area

**Metadata Inconsistency**
- Different platforms have different metadata
- No validation of metadata schema
- Hard to write platform-agnostic code

**No Message Validation**
- Empty content accepted
- No spam filtering
- No rate limiting at adapter level

**Error Handling Variance**
- Each adapter handles errors differently
- No standardized retry logic
- Platform-specific failure modes

---

## Configuration

All input adapters configured via environment variables:

```env
# Discord
DISCORD_BOT_TOKEN=your_token
DISCORD_USER_ID=your_user_id

# Telegram
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id

# Webhook
WEBHOOK_BEARER_TOKEN=123
WEBHOOK_SERVER_PORT=8080
```

Enabled in `main.py`:

```python
PRIMARY_CHAT_APP = "discord"  # or "telegram"
# Webhook input is always enabled alongside the primary chat app.
```

---

## Key Takeaways

1. **One protocol, many platforms**: All inputs implement `InputAdapter`
2. **MessageEnvelope is universal**: Core logic sees one message type
3. **Runtime manages lifecycle**: Platform login, connection handling
4. **Bus decouples input from processing**: Adapter publishes, orchestrator consumes
5. **Easy to extend**: New platform = implement protocol + wire in

---

## Related

- [Output Adapters](output.md) - Sending responses back
- [Message Bus](backends.md) - How messages flow
- [Architecture](../architecture.md) - Overall system design
