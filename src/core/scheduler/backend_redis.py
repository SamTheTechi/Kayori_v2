from __future__ import annotations

import json
from typing import Optional

try:
    import redis.asyncio as aioredis
    from redis.asyncio.lock import Lock as RedisLock
except ImportError:
    raise ImportError("Install redis: pip install redis")

from shared_types.types import Trigger

# Redis key names
_HEAP_KEY = "scheduler:heap"
_SUPPRESS_KEY = "scheduler:suppress"
_LEADER_KEY = "scheduler:leader"
_TRIGGER_PREFIX = "scheduler:trigger:"


class RedisBackend:
    """
    Redis-backed scheduler using a Sorted Set as a min-heap.

    Persistence  : Native via RDB / AOF — configure Redis itself.
    Redundancy   : RedLock single-leader election. Only one instance runs
                   the pop loop at a time; others wait for the lock to expire.
    Pub/Sub hook : Mood engine can PUBLISH to 'agent:mood:change' and this
                   backend will reactively recompute fire times (wire up via
                   subscribe_mood_changes() when mood engine is ready).

    Key layout:
      scheduler:heap              → ZSET  score=fire_at, member=trigger_id
      scheduler:suppress          → HASH  trigger_id → suppress_until (float str)
      scheduler:trigger:<id>      → STRING JSON-encoded trigger payload
      scheduler:leader            → STRING  RedLock
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379",
        # seconds before lock expires (failover window)
        leader_ttl: int = 30,
        acquire_leader: bool = True,    # set False to run as a read-only replica
    ) -> None:
        self._url = url
        self._leader_ttl = leader_ttl
        self._acquire_leader = acquire_leader
        self._client: Optional[aioredis.Redis] = None
        self._leader_lock: Optional[RedisLock] = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        self._client = aioredis.from_url(self._url, decode_responses=True)
        if self._acquire_leader:
            self._leader_lock = self._client.lock(
                _LEADER_KEY,
                timeout=self._leader_ttl,
                blocking_timeout=0,     # non-blocking — caller decides retry
            )

    async def acquire_leadership(self) -> bool:
        """
        Try to become the scheduler leader.
        Returns True if this instance is now the leader.
        Multiple instances should call this on startup; only one wins.
        """
        if self._leader_lock is None:
            return True
        try:
            return await self._leader_lock.acquire()
        except Exception:
            return False

    async def extend_leadership(self) -> None:
        """Call periodically (e.g. every leader_ttl/2 seconds) to hold the lock."""
        if self._leader_lock and await self._leader_lock.owned():
            await self._leader_lock.extend(self._leader_ttl)

    # ------------------------------------------------------------------
    # SchedulerBackend protocol
    # ------------------------------------------------------------------

    async def push(self, trigger: Trigger) -> None:
        pipe = self._client.pipeline()
        raw = json.dumps(trigger.to_dict(), separators=(",", ":"), sort_keys=True)
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

    async def close(self) -> None:
        if self._leader_lock and await self._leader_lock.owned():
            await self._leader_lock.release()
        if self._client:
            await self._client.aclose()

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
