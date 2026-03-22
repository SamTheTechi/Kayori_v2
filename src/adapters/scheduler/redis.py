from __future__ import annotations

import json
from uuid import uuid4

import redis.asyncio as redis

from src.shared_types.types import ScheduledTask


class RedisSchedulerStore:
    def __init__(self, redis_client: redis, key_prefix: str = "kayori:scheduler") -> None:
        self._client = redis_client
        self._due_key = f"{key_prefix}:due"
        self._tasks_key = f"{key_prefix}:tasks"

    async def enqueue(self, task: ScheduledTask) -> str:
        task_id = str(task.get("id") or uuid4().hex)
        due_ts = float(task.get("due_ts") or 0.0)
        payload = dict(task)
        payload["id"] = task_id
        payload["due_ts"] = due_ts
        raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
        pipe = self._client.pipeline()
        pipe.hset(self._tasks_key, task_id, raw)
        pipe.zadd(self._due_key, {task_id: due_ts})
        await pipe.execute()
        return task_id

    async def pop_due(self, *, now_ts: float, limit: int = 100) -> list[ScheduledTask]:
        if limit <= 0:
            return []

        popped = await self._client.zpopmin(self._due_key, count=limit)
        if not popped:
            return []

        due: list[tuple[str, float]] = []
        future: list[tuple[str, float]] = []
        for task_id, score in popped:
            score_f = float(score)
            if score_f <= now_ts:
                due.append((str(task_id), score_f))
            else:
                future.append((str(task_id), score_f))

        if future:
            await self._client.zadd(self._due_key, dict(future))

        if not due:
            return []

        task_ids = [task_id for task_id, _ in due]
        raws = await self._client.hmget(self._tasks_key, task_ids)
        out: list[ScheduledTask] = []

        cleanup_ids: list[str] = []
        for (task_id, score), raw in zip(due, raws, strict=False):
            cleanup_ids.append(task_id)
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            payload["id"] = str(payload.get("id") or task_id)
            payload["due_ts"] = float(payload.get("due_ts") or score)
            out.append(payload)

        if cleanup_ids:
            await self._client.hdel(self._tasks_key, *cleanup_ids)
        return out

    async def get(self, task_id: str) -> ScheduledTask | None:
        raw = await self._client.hget(self._tasks_key, task_id)
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        payload["id"] = str(payload.get("id") or task_id)
        payload["due_ts"] = float(payload.get("due_ts") or 0.0)
        return payload
