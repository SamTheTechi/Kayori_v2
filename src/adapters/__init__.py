"""Adapters for input/output, state management, message bus, and runtime integrations."""

# Input adapters
from adapters.audio.stt import WhisperSttAdapter

# Audio adapters
from adapters.audio.tts import EdgeTtsAdapter

# Message bus
from adapters.bus.in_memory import InMemoryMessageBus
from adapters.input.console_input import ConsoleInputGateway
from adapters.input.discord_input import DiscordInputAdapter
from adapters.input.telegram_input import TelegramInputAdapter
from adapters.input.webhook_input import WebhookInputAdapter
from adapters.output.console_output import ConsoleOutputAdapter

# Output adapters
from adapters.output.discord_output import DiscordOutputAdapter
from adapters.output.telegram_output import TelegramOutputAdapter
from adapters.output.webhook_output import WebhookOutputAdapter

# Runtimes
from adapters.runtime.discord_runtime import DiscordRuntime
from adapters.runtime.telegram_runtime import TelegramRuntime
from adapters.runtime.webhook_runtime import WebhookRuntime

# Safety/audit
from adapters.safety.audit_logger import JsonlAuditLogger

# State stores
from adapters.state.in_memory import InMemoryStateStore

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
    # State
    "InMemoryStateStore",
    # Runtimes
    "DiscordRuntime",
    "TelegramRuntime",
    "WebhookRuntime",
    # Audio
    "EdgeTtsAdapter",
    "WhisperSttAdapter",
    # Safety
    "JsonlAuditLogger",
]
