from __future__ import annotations

import json

import redis.asyncio as redis

from shared_types.models import MessageEnvelope


class RedisMessageBus:
    def __init__(self, redis_url: str, queue_key: str = "kayori:message_queue") -> None:
        self._client = redis.from_url(redis_url, decode_responses=True)
        self._queue_key = queue_key

    async def publish(self, envelope: MessageEnvelope) -> None:
        await self._client.lpush(self._queue_key, json.dumps(envelope.to_dict()))

    async def consume(self) -> MessageEnvelope:
        _, raw = await self._client.brpop(self._queue_key)
        payload = json.loads(raw)
        return MessageEnvelope.from_dict(payload)
