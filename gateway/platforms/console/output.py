from __future__ import annotations

from dataclasses import dataclass

from shared_types.models import OutboundMessage, MessageSource
from shared_types.protocol import OutputAdapter


@dataclass(slots=True)
class ConsoleOutputAdapter(OutputAdapter):
    name: str = "console"
    route_source: MessageSource = MessageSource.CONSOLE

    async def start(self) -> None:
        return

    async def stop(self) -> None:
        return

    async def send(self, message: OutboundMessage) -> None:
        target = message.target_user_id or message.channel_id or "unknown"
        if message.target_user_id:
            kind = "DM"
        elif message.channel_id:
            kind = "CHANNEL"
        else:
            kind = "UNKNOWN"
        print(f"[console][{kind}][{target}] {message.content}")
