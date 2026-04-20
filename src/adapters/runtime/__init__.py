from src.adapters.runtime.discord_runtime import DiscordRuntime
from src.adapters.runtime.discord_voice_runtime import DiscordVoiceRuntime
from src.adapters.runtime.telegram_runtime import TelegramRuntime

try:
    from src.adapters.runtime.webhook_runtime import WebhookRuntime
except ModuleNotFoundError:
    WebhookRuntime = None

__all__ = ["DiscordRuntime", "DiscordVoiceRuntime", "TelegramRuntime", "WebhookRuntime"]
