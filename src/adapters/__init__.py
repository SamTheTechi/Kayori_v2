"""Adapters for input/output, state management, message bus, and runtime integrations."""

# Input adapters
from src.adapters.audio.stt import WhisperSttAdapter

# Audio adapters
from src.adapters.audio.tts import EdgeTtsAdapter

# Message bus
from src.adapters.bus.in_memory import InMemoryMessageBus
from src.adapters.bus.redis_bus import RedisMessageBus

from src.adapters.input.console_input import ConsoleInputGateway
from src.adapters.input.discord_input import DiscordInputAdapter
from src.adapters.input.telegram_input import TelegramInputAdapter
from src.adapters.input.webhook_input import WebhookInputAdapter

# Output adapters
from src.adapters.output.console_output import ConsoleOutputAdapter
from src.adapters.output.discord_output import DiscordOutputAdapter
from src.adapters.output.telegram_output import TelegramOutputAdapter
from src.adapters.output.webhook_output import WebhookOutputAdapter

# Runtimes
from src.adapters.runtime.discord_runtime import DiscordRuntime
from src.adapters.runtime.telegram_runtime import TelegramRuntime
from src.adapters.runtime.webhook_runtime import WebhookRuntime

# State stores
from src.adapters.state.in_memory import InMemoryStateStore
from src.adapters.state.redis import RedisStateStore

__all__ = [
    # Input
    "DiscordInputAdapter",
    "TelegramInputAdapter",
    "ConsoleInputGateway",
    "WebhookInputAdapter",
    # Output
    "DiscordOutputAdapter",
    "TelegramOutputAdapter",
    "ConsoleOutputAdapter",
    "WebhookOutputAdapter",
    # Bus
    "InMemoryMessageBus",
    "RedisMessageBus",
    # State
    "InMemoryStateStore",
    "RedisStateStore",
    # Runtimes
    "DiscordRuntime",
    "TelegramRuntime",
    "WebhookRuntime",
    # Audio
    "EdgeTtsAdapter",
    "WhisperSttAdapter",
]
