from __future__ import annotations

import asyncio

from src.shared_types.models import MessageEnvelope


class InMemoryMessageBus:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[MessageEnvelope] = asyncio.Queue()

    async def publish(self, envelope: MessageEnvelope) -> None:
        await self._queue.put(envelope)

    async def consume(self) -> MessageEnvelope:
        return await self._queue.get()
