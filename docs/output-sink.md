# Output Sink

Routes outbound messages to the right platforms.

## What It Does

The output sink is the shared outbound dispatcher:
- Selects which adapters receive each message
- Sends to the selected outputs concurrently
- Isolates failures (one platform down does not affect all outputs)
- Manages adapter lifecycle (start/stop)

## Routing

In the current runtime, outbound chat messages are routed back through the output adapter for the active chat platform. Selection is source-based.

```python
sink = OutputSink(outputs=outputs, mode="direct")
```

Example:

```
source=DISCORD  -> Discord output adapter
source=TELEGRAM -> Telegram output adapter
```

The selection logic is source-based:
- `DISCORD` messages go to the Discord output adapter
- `TELEGRAM` messages go to the Telegram output adapter
- `multi` mode still exists in the sink type, but normal runtime routing uses `direct`

## How It Works

### Send Flow

```
1. Orchestrator builds OutboundMessage
2. Calls sink.send(message)
3. Sink selects target adapters
4. Sends to all concurrently (asyncio.gather)
5. Logs failures per adapter
6. Returns without raising adapter send failures
```

### Selection Logic

```python
def _select_outputs(message):
    if mode == "multi":
        return list(outputs)

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
    source=MessageSource.DISCORD,
    content="Here's your answer!",
    channel_id="channel456",
    target_user_id="user123",
    reply_to_message_id="msg789",
    mention_author=True,
    voice_mode=False,
    metadata={...},
    audio=None,
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
- One adapter failing does not abort the rest of the send operation

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
    voice_mode=bool(envelope.voice_mode),
    metadata=...,
    reply_to_message_id=envelope.message_id,
    mention_author=bool(envelope.channel_id and not envelope.target_user_id),
)

# Send via sink
await output_sink.send(outbound)
```

Tools also use the sink:
```python
# ReminderTool sends reminders through sink
await self._output.send(reminder_message)
```

## File Reference

[`agent/orchestration/outputsink.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/agent/orchestration/outputsink.py)
