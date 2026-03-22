from __future__ import annotations

import asyncio
import heapq
from itertools import count
from uuid import uuid4

from src.shared_types.types import ScheduledTask


class InMemorySchedulerStore:
    def __init__(self) -> None:
        self._tasks: dict[str, ScheduledTask] = {}
        self._heap: list[tuple[float, int, str]] = []
        self._seq = count()
        self._lock = asyncio.Lock()

    async def enqueue(self, task: ScheduledTask) -> str:
        async with self._lock:
            task_id = str(task.get("id") or uuid4().hex)
            due_ts = float(task.get("due_ts") or 0.0)
            payload = dict(task)
            payload["id"] = task_id
            payload["due_ts"] = due_ts
            self._tasks[task_id] = payload
            heapq.heappush(self._heap, (due_ts, next(self._seq), task_id))
            return task_id

    async def pop_due(self, *, now_ts: float, limit: int = 100) -> list[ScheduledTask]:
        if limit <= 0:
            return []

        out: list[ScheduledTask] = []
        async with self._lock:
            while self._heap and len(out) < limit:
                due_ts, _, task_id = self._heap[0]
                if due_ts > now_ts:
                    break
                heapq.heappop(self._heap)
                task = self._tasks.pop(task_id, None)
                if task is None:
                    continue
                out.append(dict(task))
        return out

    async def get(self, task_id: str) -> ScheduledTask | None:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            return dict(task)
