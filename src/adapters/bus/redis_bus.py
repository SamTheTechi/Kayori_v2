from __future__ import annotations

import json
from redis.asyncio import Redis

from src.shared_types.models import MessageEnvelope


class RedisMessageBus:
    def __init__(self, redis_client: Redis, queue_key: str = "kayori:message_queue") -> None:
        self._client = redis_client
        self._queue_key = queue_key

    async def publish(self, envelope: MessageEnvelope) -> None:
        await self._client.lpush(self._queue_key, json.dumps(envelope.to_dict()))

    async def consume(self) -> MessageEnvelope:
        _, raw = await self._client.brpop(self._queue_key)
        payload = json.loads(raw)
        return MessageEnvelope.from_dict(payload)
