from __future__ import annotations

from dataclasses import dataclass
from shared_types.models import OutboundMessage


@dataclass(slots=True)
class ConsoleOutputAdapter:
    name: str = "console"

    async def start(self) -> None:
        return

    async def stop(self) -> None:
        return

    async def send(self, message: OutboundMessage) -> None:
        target = message.target_user_id or message.channel_id or "unknown"
        kind = "DM" if message.is_dm else "CHANNEL"
        extra = ""
        if message.attachments:
            media = ", ".join(
                f"{item.kind}:{item.url or item.filename or '[embedded]'}" for item in message.attachments[:4]
            )
            extra = f" | media={media}"
        print(f"[console][{kind}][{target}] {message.content}{extra}")
