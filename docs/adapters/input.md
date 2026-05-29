# Input Adapters

Input adapters listen to external sources and publish `MessageEnvelope` objects to the message bus.

## Available Input Adapters

| Adapter | Source | Notes |
|---------|--------|-------|
| `DiscordInputAdapter` | Discord text messages | Uses `DiscordRuntime` |
| `TelegramInputAdapter` | Telegram updates | Supports text and audio |
| `WebhookInputAdapter` | HTTP routes on `WebhookRuntime` | Handles text and uploaded audio |
| `ConsoleInputGateway` | stdin | Local testing path |

## How Input Adapters Work

General flow:

```text
Platform Event -> Input Adapter -> MessageEnvelope -> MessageBus
```

Every adapter publishes a `MessageEnvelope` with the normalized source, routing fields, and any platform metadata that the runtime needs later.

## MessageEnvelope Structure

```python
MessageEnvelope(
    source=MessageSource.DISCORD,
    content="Hello bot!",
    channel_id="channel456",
    author_id="user123",
    message_id="msg789",
    target_user_id=None,
    audio=None,
    voice_mode=False,
    metadata={...},
)
```

## DiscordInputAdapter

`DiscordInputAdapter` registers a message handler on `DiscordRuntime`, acquires the runtime, and publishes one envelope per incoming Discord text message.

Current envelope behavior:
- `source=MessageSource.DISCORD`
- DMs are routed with `target_user_id`
- guild channels are routed with `channel_id`
- metadata currently includes `author_display_name`

## TelegramInputAdapter

`TelegramInputAdapter` registers an update handler on `TelegramRuntime`, optionally filters by `allowed_chat_ids`, and publishes envelopes for text, caption, voice, or audio messages.

Current behavior:
- private chats use `target_user_id`
- group chats use `channel_id`
- audio attachments are downloaded through the runtime and stored in `audio`
- `voice_mode` is set when an audio payload exists

## WebhookInputAdapter

`WebhookInputAdapter` registers HTTP routes on `WebhookRuntime`:
- `POST /webhooks/text`
- `POST /webhooks/audio`

Current behavior:
- `/webhooks/text` accepts JSON and returns the matching webhook response payload
- `/webhooks/audio` accepts multipart form data with uploaded audio
- both routes publish `MessageEnvelope` objects and wait on the runtime’s pending response registry
- bearer authentication is enforced by the runtime route wrapper

The adapter does not run STT itself. It stores uploaded audio and passes language, prompt, and TTS-related fields through envelope metadata.

## ConsoleInputGateway

`ConsoleInputGateway` reads stdin asynchronously, wraps each entered line in a console envelope, and publishes it to the bus.

Current behavior:
- uses `channel_id="console"` and `author_id="local-user"` by default
- exits on `exit` or `quit`
- sets `metadata={"transport": "stdin"}`

## Creating a Custom Input Adapter

```python
from shared_types.protocol import MessageBus
from shared_types.models import MessageEnvelope, MessageSource

class MyPlatformInput:
    name = "my-platform"

    def __init__(self, bus: MessageBus):
        self.bus = bus

    async def start(self) -> None:
        ...

    async def stop(self) -> None:
        ...

    async def publish_event(self, text: str) -> None:
        await self.bus.publish(
            MessageEnvelope(
                source=MessageSource.WEBHOOK,
                content=text,
            )
        )
```

Register the adapter in the input builder path in `main.py`.

## Configuration

Current runtime wiring is driven from `main.py` and environment variables such as:

```env
PRIMARY_CHAT_APP=discord
DISCORD_BOT_TOKEN=
TELEGRAM_BOT_TOKEN=
WEBHOOK_BEARER_TOKEN=
WEBHOOK_SERVER_PORT=8080
```

## File References

- [`gateway/platforms/discord/input.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/gateway/platforms/discord/input.py)
- [`gateway/platforms/telegram/input.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/gateway/platforms/telegram/input.py)
- [`gateway/platforms/webhook/input.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/gateway/platforms/webhook/input.py)
- [`gateway/platforms/console/input.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/gateway/platforms/console/input.py)

## Related

- [Output Adapters](output.md)
- [Backend Adapters](backends.md)
- [Architecture](../architecture.md)
