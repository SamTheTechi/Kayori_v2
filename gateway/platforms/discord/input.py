from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import discord

from gateway.platforms.discord.runtime import DiscordMessageHandler, DiscordRuntime

from config.logging import get_logger
from shared_types.models import MessageEnvelope, MessageSource
from shared_types.protocol import InputAdapter, MessageBus

logger = get_logger("input.discord")


@dataclass(slots=True)
class DiscordInputAdapter(InputAdapter):
    runtime: DiscordRuntime
    bus: MessageBus
    name: str = "discord"

    _stop_event: asyncio.Event = field(
        default_factory=asyncio.Event, init=False, repr=False
    )
    _handler: DiscordMessageHandler | None = field(
        default=None, init=False, repr=False)
    _acquired: bool = field(default=False, init=False, repr=False)

    async def start(self) -> None:
        self._stop_event.clear()
        self._handler = self._handle_message
        await self.runtime.register_message_handler(self._handler)
        await self.runtime.acquire()
        self._acquired = True

        try:
            await self._stop_event.wait()
        finally:
            await self._cleanup()

    async def stop(self) -> None:
        self._stop_event.set()
        await self._cleanup()

    async def _cleanup(self) -> None:
        handler = self._handler
        self._handler = None
        if handler is not None:
            await self.runtime.unregister_message_handler(handler)
        if self._acquired:
            self._acquired = False
            await self.runtime.release()

    async def _handle_message(self, message: discord.Message) -> None:
        content = (message.content or "").strip()

        envelope = MessageEnvelope(
            source=MessageSource.DISCORD,
            content=content,
            author_id=str(message.author.id),
            target_user_id=(
                str(message.author.id)
                if isinstance(message.channel, discord.DMChannel)
                else None
            ),
            channel_id=(
                None
                if isinstance(message.channel, discord.DMChannel)
                else str(message.channel.id)
            ),
            message_id=str(message.id),
            metadata={
                "author_display_name": message.author.display_name,
            },
        )
        await self.bus.publish(envelope)
