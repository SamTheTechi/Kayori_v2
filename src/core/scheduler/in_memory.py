from __future__ import annotations

import asyncio
import heapq

from src.shared_types.types import Trigger


class InMemorySchedulerBackend:
    """
    Pure in-memory scheduler backend backed by a min-heap.

    No persistence. No redundancy.
    Suitable for: development, testing, single-process embedded use.
    """

    def __init__(self) -> None:
        self._heap: list[tuple[float, str, Trigger]] = []
        self._suppressed: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def push(self, trigger: Trigger) -> None:
        async with self._lock:
            heapq.heappush(self._heap, (trigger.fire_at,
                           trigger.trigger_id, trigger))

    async def pop_due(self, now: float) -> list[Trigger]:
        due: list[Trigger] = []
        async with self._lock:
            while self._heap and self._heap[0][0] <= now:
                _, tid, trigger = heapq.heappop(self._heap)
                suppress_until = self._suppressed.get(tid, 0)
                if suppress_until > now:
                    # Still suppressed — push back to suppression end time
                    trigger.fire_at = suppress_until
                    heapq.heappush(self._heap, (trigger.fire_at, tid, trigger))
                    continue
                due.append(trigger)
        return due

    async def reschedule(self, trigger: Trigger) -> None:
        await self.push(trigger)

    async def suppress(self, trigger_id: str, until: float) -> None:
        async with self._lock:
            self._suppressed[trigger_id] = until

    async def remove(self, trigger_id: str) -> None:
        async with self._lock:
            self._heap = [
                (t, tid, tr) for t, tid, tr in self._heap if tid != trigger_id
            ]
            heapq.heapify(self._heap)
            self._suppressed.pop(trigger_id, None)

    async def list_pending(self) -> list[Trigger]:
        async with self._lock:
            return [tr for _, _, tr in sorted(self._heap)]

    async def restore(self) -> list[Trigger]:
        return []
