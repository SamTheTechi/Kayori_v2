from __future__ import annotations

import json

from redis.asyncio import Redis

from src.shared_types.types import Trigger

# Redis key names
_HEAP_KEY = "scheduler:heap"
_SUPPRESS_KEY = "scheduler:suppress"
_TRIGGER_PREFIX = "scheduler:trigger:"


class RedisSchedulerBackend:
    def __init__(
        self,
        redis_client: Redis,
    ) -> None:
        self._client = redis_client

    # ------------------------------------------------------------------
    # SchedulerBackend protocol
    # ------------------------------------------------------------------

    async def push(self, trigger: Trigger) -> None:
        pipe = self._client.pipeline()
        raw = json.dumps(trigger.to_dict(), separators=(
            ",", ":"), sort_keys=True)
        pipe.set(_TRIGGER_PREFIX + trigger.trigger_id, raw)
        pipe.zadd(_HEAP_KEY, {trigger.trigger_id: trigger.fire_at})
        await pipe.execute()

    async def pop_due(self, now: float) -> list[Trigger]:
        # Atomically pop all members with score <= now
        # ZPOPMIN is not range-based — use ZRANGEBYSCORE + ZREM in a pipeline
        due_ids: list[str] = await self._client.zrangebyscore(
            _HEAP_KEY, min="-inf", max=now
        )
        if not due_ids:
            return []

        # Check suppression
        suppress_map: dict = await self._client.hgetall(_SUPPRESS_KEY)
        triggers: list[Trigger] = []

        pipe = self._client.pipeline()
        for tid in due_ids:
            suppress_until = float(suppress_map.get(tid, 0))
            if suppress_until > now:
                # Re-enqueue at suppression end time
                pipe.zadd(_HEAP_KEY, {tid: suppress_until})
            else:
                pipe.zrem(_HEAP_KEY, tid)
                triggers.append(tid)
        await pipe.execute()

        # Fetch payloads for non-suppressed triggers
        result: list[Trigger] = []
        for tid in triggers:
            raw = await self._client.get(_TRIGGER_PREFIX + tid)
            if raw:
                result.append(Trigger.from_dict(json.loads(raw)))
        return result

    async def reschedule(self, trigger: Trigger) -> None:
        await self.push(trigger)

    async def suppress(self, trigger_id: str, until: float) -> None:
        await self._client.hset(_SUPPRESS_KEY, trigger_id, str(until))

    async def remove(self, trigger_id: str) -> None:
        pipe = self._client.pipeline()
        pipe.zrem(_HEAP_KEY, trigger_id)
        pipe.delete(_TRIGGER_PREFIX + trigger_id)
        pipe.hdel(_SUPPRESS_KEY, trigger_id)
        await pipe.execute()

    async def list_pending(self) -> list[Trigger]:
        entries = await self._client.zrange(_HEAP_KEY, 0, -1, withscores=True)
        triggers = []
        for tid, score in entries:
            raw = await self._client.get(_TRIGGER_PREFIX + tid)
            if raw:
                triggers.append(Trigger.from_dict(json.loads(raw)))
        return triggers

    async def restore(self) -> list[Trigger]:
        """
        Called once on startup. Returns all triggers still in the heap so
        the scheduler can apply missed trigger policies before the main loop.
        """
        return await self.list_pending()

    # ------------------------------------------------------------------
    # Mood engine hook (wire up later)
    # ------------------------------------------------------------------

    async def subscribe_mood_changes(self, callback) -> None:
        """
        Subscribe to 'agent:mood:change' pub/sub channel.
        When mood engine is ready, it publishes JSON mood state here.
        callback(mood_dict) will be called on each message.

        Usage:
            await backend.subscribe_mood_changes(on_mood_change)
        """
        pubsub = self._client.pubsub()
        await pubsub.subscribe("agent:mood:change")
        async for message in pubsub.listen():
            if message["type"] == "message":
                import json
                mood = json.loads(message["data"])
                await callback(mood)
