# Output Adapters

Output adapters deliver `OutboundMessage` objects to external platforms.

## Available Output Adapters

| Adapter | Target | Notes |
|---------|--------|-------|
| `DiscordOutputAdapter` | Discord | Supports text replies |
| `TelegramOutputAdapter` | Telegram | Supports text and audio sends |
| `WebhookOutputAdapter` | HTTP targets and webhook response completion | Posts outbound payloads and resolves pending webhook responses |
| `ConsoleOutputAdapter` | stdout | Local development path |

## How Output Adapters Work

General flow:

```text
AgentOrchestrator -> OutboundMessage -> OutputSink -> OutputAdapter
```

`OutputSink` selects the adapters. Each adapter handles route resolution and the platform-specific send.

## OutboundMessage Structure

```python
OutboundMessage(
    source=MessageSource.DISCORD,
    content="Here's your answer!",
    channel_id="channel456",
    target_user_id="user123",
    audio=None,
    voice_mode=False,
    metadata={...},
    reply_to_message_id="msg789",
    mention_author=True,
)
```

## Output Sink Routing

In normal runtime use, `OutputSink` runs in `direct` mode and selects adapters by `route_source == message.source`.

Current production composition in `main.py`:
- one primary output adapter for Discord or Telegram
- one webhook output adapter

The sink type still supports `multi`, but normal routing remains source-based.

## DiscordOutputAdapter

`DiscordOutputAdapter` resolves either a DM route or a channel route, then sends text through `DiscordRuntime`.

Current behavior:
- supports explicit routing overrides through `discord_channel_id` and `discord_user_id` metadata
- replies to the original message only when `message.source == DISCORD` and `reply_to_message_id` is present

## TelegramOutputAdapter

`TelegramOutputAdapter` resolves a chat ID from metadata, `target_user_id`, `channel_id`, or the configured default chat.

Current behavior:
- chunks long messages before sending
- replies to the original Telegram message when `reply_to_message_id` is present
- uses `send_voice()` for OGG or voice-mode payloads
- uses `send_audio()` for other audio payloads

## WebhookOutputAdapter

`WebhookOutputAdapter` does two things:
- resolves pending synchronous webhook responses through `WebhookRuntime`
- posts the outbound payload to configured HTTP target URLs

Current behavior:
- if the outbound metadata contains a webhook envelope ID, the runtime response future is resolved first
- text and audio payloads are forwarded to every configured target with `httpx.AsyncClient`
- bearer auth is added when configured
- target failures are logged per URL

TTS is not implemented inside the output adapter. Audio generation happens earlier in the orchestrator before the outbound message reaches the sink.

## ConsoleOutputAdapter

`ConsoleOutputAdapter` prints the outbound content to stdout with a simple route label derived from `target_user_id` or `channel_id`.

## Creating a Custom Output Adapter

```python
from shared_types.models import MessageSource, OutboundMessage

class MyPlatformOutput:
    name = "my-platform"
    route_source = MessageSource.WEBHOOK

    async def start(self) -> None:
        ...

    async def stop(self) -> None:
        ...

    async def send(self, message: OutboundMessage) -> None:
        ...
```

Register the adapter in the output builder path in `main.py`.

## Configuration

Current output wiring is driven from `main.py` and environment variables such as:

```env
PRIMARY_CHAT_APP=discord
DISCORD_USER_ID=
TELEGRAM_CHAT_ID=
WEBHOOK_OUTPUT_URLS=
WEBHOOK_OUTPUT_BEARER_TOKEN=
OUTPUT_SINK_MODE=direct
```

## File References

- [`gateway/platforms/discord/output.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/gateway/platforms/discord/output.py)
- [`gateway/platforms/telegram/output.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/gateway/platforms/telegram/output.py)
- [`gateway/platforms/webhook/output.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/gateway/platforms/webhook/output.py)
- [`gateway/platforms/console/output.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/gateway/platforms/console/output.py)
- [`agent/orchestration/outputsink.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/agent/orchestration/outputsink.py)

## Related

- [Input Adapters](input.md)
- [Output Sink](../output-sink.md)
- [Architecture](../architecture.md)
