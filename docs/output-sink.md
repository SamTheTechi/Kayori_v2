# Output Sink

Routes outbound messages to the right platforms.

## What It Does

The output sink is the shared outbound dispatcher:
- 📨 Selects which adapters receive each message
- 🚀 Sends to one or many outputs concurrently
- 🛡️ Isolates failures (one platform down ≠ all down)
- 🔄 Manages adapter lifecycle (start/stop)

## Two Routing Modes

### Direct Mode (Default)

Routes back to **same platform** message came from:

```
Discord message → Discord response
Telegram message → Telegram response
```

```python
sink = OutputSink(outputs=outputs, mode="direct")
```

**How it works:**
- Matches `message.source` to adapter's `route_source`
- Discord source → Discord output adapter only
- Keeps responses on originating platform

### Multi Mode

**Broadcasts** to all configured outputs:

```
One message → Discord + Telegram + Webhook
```

```python
sink = OutputSink(outputs=outputs, mode="multi")
```

**Use cases:**
- Testing multiple platforms
- Mirroring conversations
- Debugging adapters

## How It Works

### Send Flow

```
1. Orchestrator builds OutboundMessage
2. Calls sink.send(message)
3. Sink selects target adapters
4. Sends to all concurrently (asyncio.gather)
5. Logs failures per adapter
6. Returns (doesn't crash on failures)
```

### Selection Logic

```python
def _select_outputs(message):
    if mode == "multi":
        return all_outputs  # Broadcast
    
    # Direct mode: match source
    return [
        output for output in outputs
        if output.route_source == message.source
    ]
```

**Example:**
- `source=DISCORD` → DiscordOutputAdapter only
- `source=TELEGRAM` → TelegramOutputAdapter only

## OutboundMessage Structure

```python
OutboundMessage(
    source=MessageSource.DISCORD,       # Original source
    content="Here's your answer!",       # Response text
    channel_id="channel456",             # Where to send
    target_user_id="user123",            # Who to reply to
    reply_to_message_id="msg789",        # Thread reply (optional)
    mention_author=True,                 # @mention user (optional)
    metadata={...}                       # Extra data
)
```

## Lifecycle Management

```python
# Start outputs in order
await sink.start()

# Stop outputs in reverse order
await sink.stop()
```

**Why reverse order?**
- Teardown dependencies safely
- Last started = first stopped
- Prevents orphaned connections

## Error Handling

Uses `asyncio.gather(return_exceptions=True)`:
- All adapters send concurrently
- Failures caught and logged
- One adapter failing doesn't stop others
- System continues if Discord down, Telegram works

**Logging:**
```python
# No targets
logger.warning("output_dropped_no_targets", ...)

# Adapter failure
logger.error("output_send_failed", ...)
```

## Runtime Usage

From orchestrator:
```python
# Build outbound message
outbound = OutboundMessage(
    source=envelope.source,
    content=reply_text,
    channel_id=envelope.channel_id,
    target_user_id=envelope.target_user_id,
    reply_to_message_id=envelope.message_id
)

# Send via sink
await output_sink.send(outbound)
```

Tools also use the sink:
```python
# ReminderTool sends reminders through sink
await self._output.send(reminder_message)
```

## Pros and Cons

### ✅ Strengths

**Simple Abstraction**
- One interface for all outputs
- Orchestrator doesn't know adapters
- Clean separation

**Flexible Routing**
- Direct mode for normal use
- Multi mode for testing/broadcast
- Easy to switch

**Failure Isolation**
- Concurrent sends
- Per-adapter error catching
- No cascade failures

**Lifecycle Management**
- Ordered start/stop
- Reverse teardown
- Graceful shutdown

**Visibility**
- Dropped messages logged
- Failures logged per adapter
- Easy to debug

### ❌ Limitations

**Simple Routing**
- Only matches source
- No complex rules
- No priority/fallback

**No Transformation**
- Adapters receive raw message
- No auto-formatting
- Platform-specific handling manual

**No Retries**
- Failed sends just logged
- No retry logic
- No dead letter queue

**Assumes Compatibility**
- All outputs accept same shape
- No capability checking
- May fail on platform limits

**Synchronous Within Async**
- Each adapter's send() blocks
- Slow adapter delays completion
- No per-adapter timeout

---

## File Reference

[`src/core/outputsink.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/src/core/outputsink.py)
