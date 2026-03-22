from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import discord

from src.logger import get_logger

DiscordMessageHandler = Callable[[discord.Message], Awaitable[None]]
logger = get_logger("runtime.discord")


@dataclass(slots=True)
class DiscordRuntime:
    token: str
    name: str = "discord-runtime"

    _client: discord.Client | None = field(default=None, init=False, repr=False)
    _start_task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _ready: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)
    _ref_count: int = field(default=0, init=False, repr=False)
    _handlers: list[DiscordMessageHandler] = field(
        default_factory=list, init=False, repr=False
    )

    async def register_message_handler(self, handler: DiscordMessageHandler) -> None:
        async with self._lock:
            if handler not in self._handlers:
                self._handlers.append(handler)

    async def unregister_message_handler(self, handler: DiscordMessageHandler) -> None:
        async with self._lock:
            self._handlers = [item for item in self._handlers if item is not handler]

    async def acquire(self) -> None:
        async with self._lock:
            self._ref_count += 1
            if self._ref_count == 1:
                self._start_locked()

        await self._wait_until_ready()

    async def release(self) -> None:
        start_task: asyncio.Task[None] | None = None
        client: discord.Client | None = None

        async with self._lock:
            if self._ref_count == 0:
                return

            self._ref_count -= 1
            if self._ref_count > 0:
                return

            start_task = self._start_task
            client = self._client
            self._start_task = None
            self._client = None
            self._ready.clear()

        if client is not None and not client.is_closed():
            await client.close()
        if start_task is not None:
            await asyncio.gather(start_task, return_exceptions=True)

    @property
    def client(self) -> discord.Client:
        if self._client is None:
            raise RuntimeError("Discord runtime client is not initialized.")
        return self._client

    def _start_locked(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True

        client = discord.Client(intents=intents)

        @client.event
        async def on_ready() -> None:
            self._ready.set()
            await logger.info(
                "discord_ready",
                "Discord runtime connected.",
                context={"user": str(client.user)},
            )

        @client.event
        async def on_message(message: discord.Message) -> None:
            if message.author == client.user:
                return

            handlers = list(self._handlers)
            for handler in handlers:
                try:
                    await handler(message)
                except Exception as exc:
                    await logger.exception(
                        "discord_handler_failed",
                        "Discord message handler failed.",
                        context={
                            "message_id": str(message.id),
                            "author_id": str(message.author.id),
                            "channel_id": str(message.channel.id),
                        },
                        error=exc,
                    )

        self._client = client
        self._start_task = asyncio.create_task(
            client.start(self.token), name="discord-runtime-start"
        )

    async def _wait_until_ready(self) -> None:
        while not self._ready.is_set():
            start_task = self._start_task
            if start_task is not None and start_task.done():
                exc = start_task.exception()
                raise RuntimeError("Discord runtime failed to start.") from exc
            await asyncio.sleep(0.05)
