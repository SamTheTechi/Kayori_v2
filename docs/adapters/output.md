# Output Adapters

Output adapters deliver Kayori's responses to external platforms.

## Available Output Adapters

| Adapter | Platform | Special Features |
|---------|----------|------------------|
| DiscordOutputAdapter | Discord | Reply threading, mentions |
| TelegramOutputAdapter | Telegram | Group/DM support |
| WebhookOutputAdapter | HTTP REST | TTS, multiple targets |
| ConsoleOutputAdapter | CLI | Development/testing |

---

## How Output Adapters Work

### General Flow

```
Orchestrator → OutboundMessage → OutputSink → OutputAdapter → Platform
```

### OutboundMessage Structure

```python
OutboundMessage(
    source=MessageSource.DISCORD,       # Original source
    content="Here's your answer!",       # Response text
    channel_id="channel456",             # Where to send
    target_user_id="user123",            # Who to reply to
    reply_to_message_id="msg789",        # Thread reply (optional)
    mention_author=True,                 @mention user (optional)
    metadata={...}                       # Extra data
)
```

---

## Output Sink Routing

Before reaching output adapters, messages pass through `OutputSink`:

### Direct Mode (Default)
- Routes back to **same platform** message came from
- Discord message → Discord response
- Telegram message → Telegram response

### Multi Mode
- **Broadcasts** to all configured outputs
- Useful for testing/mirroring
- One message → Discord + Telegram + Webhook

```python
# In main.py
output_dispatcher = OutputSink(outputs=outputs, mode="direct")
```

---

## DiscordOutputAdapter

### What It Does

Sends responses to Discord channels.

### Setup

```python
discord_output = DiscordOutputAdapter(
    runtime=discord_runtime,
    default_channel_id=None,
    default_user_id=discord_user_id
)
```

### Features

- Sends messages to Discord channels
- Reply threading via `reply_to_message_id`
- @mention support with `mention_author`
- Uses Discord runtime for API access

### Pros
✅ Native Discord formatting  
✅ Reply threads work naturally  
✅ Mentions notify users  

### Cons
❌ Requires Discord runtime  
❌ Rate limited by Discord API  
❌ Message length limits (2000 chars)  

---

## TelegramOutputAdapter

### What It Does

Sends responses to Telegram chats/groups.

### Setup

```python
telegram_output = TelegramOutputAdapter(
    runtime=telegram_runtime,
    default_chat_id=telegram_chat_id
)
```

### Features

- Sends messages to Telegram chats
- Works in groups and DMs
- Default chat ID fallback
- Uses Telegram runtime

### Pros
✅ Native Telegram formatting  
✅ Works in groups  
✅ Supports Telegram features  

### Cons
❌ Requires Telegram runtime  
❌ Rate limited by Telegram API  
❌ Markdown parsing errors can fail sends  

---

## WebhookOutputAdapter

### What It Does

Sends responses via HTTP POST to custom endpoints. Includes TTS support.

### Setup

```python
webhook_output = WebhookOutputAdapter(
    targets=["http://example.com/callback"],
    runtime=webhook_runtime,
    tts=webhook_tts,  # EdgeTTS adapter
    bearer_token=webhook_token
)
```

### Features

- HTTP POST to configured targets
- Bearer token authentication
- Text-to-speech via EdgeTTS
- Multiple target URLs
- Audio generation for voice responses

### TTS Integration

```python
# EdgeTTS converts text to speech
tts = EdgeTtsAdapter(
    api_key="123",
    base_url="http://localhost:5050/v1"
)

# Webhook output includes audio
webhook_output = WebhookOutputAdapter(
    targets=[...],
    tts=tts
)
```

### Pros
✅ Platform agnostic  
✅ Custom integrations  
✅ Voice/audio support  
✅ Multiple targets  

### Cons
❌ Requires HTTP server  
❌ Target must be reachable  
❌ TTS adds latency  

---

## ConsoleOutputAdapter

### What It Does

Prints responses to stdout for testing.

### Setup

```python
console_output = ConsoleOutputAdapter()
```

### Features

- Simple print to console
- No configuration needed
- Great for development
- Instant feedback

### Pros
✅ Zero setup  
✅ Perfect for testing  
✅ No dependencies  

### Cons
❌ Not for production  
❌ No platform features  
❌ Single user only  

---

## Creating a Custom Output Adapter

### Step 1: Implement Protocol

```python
from src.shared_types.protocol import OutputAdapter
from src.shared_types.models import OutboundMessage, MessageSource

class MyPlatformOutput(OutputAdapter):
    name = "my_platform"
    route_source = MessageSource.WEBHOOK  # Match this source
    
    def __init__(self, runtime):
        self.runtime = runtime
    
    async def start(self):
        # Initialize connection
        pass
    
    async def stop(self):
        # Clean up
        pass
    
    async def send(self, message: OutboundMessage):
        # Deliver to platform
        await self.runtime.send_message(
            channel_id=message.channel_id,
            content=message.content,
            reply_to=message.reply_to_message_id
        )
```

### Step 2: Wire in main.py

```python
from src.adapters.output.my_platform import MyPlatformOutput

outputs.append(MyPlatformOutput(runtime=my_runtime))
```

---

## Output Adapter Pros and Cons (Overall)

### ✅ Strengths

**Platform Flexibility**
- Same response logic works everywhere
- Easy to add new platforms
- Test with console output

**Failure Isolation**
- One adapter failing doesn't crash others
- Output sink catches errors per-adapter
- System continues if Discord down, Telegram works

**Routing Modes**
- Direct mode for normal use
- Multi mode for testing/broadcasting
- Flexible deployment options

**Lifecycle Management**
- Clean start/stop in order
- Reverse order teardown
- Graceful shutdown

### ❌ Limitations

**No Message Transformation**
- Adapters receive raw `OutboundMessage`
- Platform-specific formatting manual
- No automatic length truncation

**Limited Error Recovery**
- Failed sends just logged
- No retry logic
- No dead letter queue

**Routing Simplicity**
- Direct mode only matches source
- No complex routing rules
- No priority/fallback logic

**Synchronous Within Async**
- Each adapter's `send()` blocks
- Slow adapter delays gather completion
- No timeout per adapter

---

## Configuration

Environment variables:

```env
# Discord
DISCORD_USER_ID=target_user_id

# Telegram
TELEGRAM_CHAT_ID=target_chat_id

# Webhook
WEBHOOK_OUTPUT_URLS=http://target1,http://target2
WEBHOOK_OUTPUT_BEARER_TOKEN=token

# TTS
EDGE_TTS_BASE_URL=http://localhost:5050/v1
EDGE_TTS_API_KEY=123

# Sink Mode
OUTPUT_SINK_MODE=direct  # or "multi"
```

Enabled in `main.py`:

```python
PRIMARY_CHAT_APP = "discord"  # or "telegram"
# Webhook output is always enabled alongside the primary chat app.
```

---

## Output Selection Logic

From `OutputSink._select_outputs()`:

```python
def _select_outputs(self, message: OutboundMessage) -> list[OutputAdapter]:
    if self.mode == "multi":
        return list(self.outputs)  # All adapters
    
    # Direct mode: match source
    return [
        output for output in self.outputs 
        if output.route_source == message.source
    ]
```

**Example:**
- Discord message → `source=DISCORD` → DiscordOutputAdapter only
- Telegram message → `source=TELEGRAM` → TelegramOutputAdapter only

---

## Key Takeaways

1. **One protocol, many platforms**: All outputs implement `OutputAdapter`
2. **Sink handles routing**: Direct or multi mode
3. **Failures isolated**: One down ≠ all down
4. **TTS integration**: Webhook output includes audio
5. **Easy to extend**: New platform = implement protocol + wire in

---

## Related

- [Input Adapters](input.md) - Receiving messages
- [Output Sink](../output-sink.md) - Routing logic
- [Architecture](../architecture.md) - Overall system design
