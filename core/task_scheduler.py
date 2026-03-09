from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from shared_types.models import MessageEnvelope, MessageSource
from shared_types.protocol import MessageBus, SchedulerStore
from shared_types.types import ScheduleRequest, ScheduledTask


@dataclass(slots=True)
class TaskScheduler:
    store: SchedulerStore
    bus: MessageBus
    fallback_target_user_id: str | None = None
    poll_interval_seconds: float = 1.0
    batch_size: int = 50
    _worker_task: asyncio.Task[None] | None = field(
        default=None, init=False, repr=False)

    async def schedule(self, request: ScheduleRequest) -> str:
        task = _build_task(
            request, fallback_target_user_id=self.fallback_target_user_id)
        return await self.store.enqueue(task)

    async def start(self) -> None:
        if self._worker_task and not self._worker_task.done():
            return
        self._worker_task = asyncio.create_task(
            self.run_forever(), name="task-scheduler")

    async def stop(self) -> None:
        task = self._worker_task
        self._worker_task = None
        if task is None:
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def run_forever(self) -> None:
        while True:
            await self.tick()
            await asyncio.sleep(max(0.05, self.poll_interval_seconds))

    async def tick(self) -> int:
        now_ts = time.time()
        tasks = await self.store.pop_due(now_ts=now_ts, limit=max(1, self.batch_size))
        sent = 0
        for task in tasks:
            envelope = _task_to_envelope(task)
            if envelope is None:
                continue
            try:
                await self.bus.publish(envelope)
                sent += 1
            except Exception as exc:
                print(f"[task_scheduler] publish failed (task_id={
                      task.get('id')}): {exc}")
        return sent


def _build_task(request: ScheduleRequest, *, fallback_target_user_id: str | None) -> ScheduledTask:
    content = str(request.get("content") or "").strip()
    if not content:
        raise ValueError("ScheduleRequest.content is required.")

    mode = str(request.get("mode") or "exact").strip().lower()
    if mode not in {"exact", "window"}:
        raise ValueError("ScheduleRequest.mode must be 'exact' or 'window'.")

    due_ts = _resolve_due_ts(request, mode=mode)
    if due_ts < time.time():
        due_ts = time.time()

    task: ScheduledTask = {
        "mode": mode,  # type: ignore[typeddict-item]
        "due_ts": due_ts,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "content": content,
        "source": request.get("source") or MessageSource.INTERNAL,
        "target_user_id": _maybe_str(
            request.get("target_user_id") or fallback_target_user_id
        ),
        "channel_id": _maybe_str(request.get("channel_id")),
        "metadata": dict(request.get("metadata") or {}),
    }
    return task


def _resolve_due_ts(request: ScheduleRequest, *, mode: str) -> float:
    if mode == "window":
        start_ts = _as_unix_ts(request.get("window_start"))
        end_ts = _as_unix_ts(request.get("window_end"))
        if end_ts < start_ts:
            raise ValueError(
                "ScheduleRequest.window_end must be >= window_start.")
        return random.uniform(start_ts, end_ts)
    return _as_unix_ts(request.get("run_at"))


def _as_unix_ts(value: str | float | int | None) -> float:
    if value is None:
        raise ValueError("Schedule time is missing.")
    if isinstance(value, (float, int)):
        return float(value)

    raw = str(value).strip()
    if not raw:
        raise ValueError("Schedule time is empty.")

    normalized = raw.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _task_to_envelope(task: ScheduledTask) -> MessageEnvelope | None:
    content = str(task.get("content") or "").strip()
    if not content:
        return None

    metadata = dict(task.get("metadata") or {})
    metadata.setdefault("kind", "scheduled_task")
    metadata["schedule_mode"] = str(task.get("mode") or "exact")
    if task.get("id"):
        metadata["schedule_task_id"] = str(task["id"])
    if task.get("due_ts") is not None:
        metadata["schedule_due_ts"] = float(task["due_ts"])

    return MessageEnvelope(
        source=_message_source(task.get("source")),
        content=content,
        target_user_id=_maybe_str(task.get("target_user_id")),
        channel_id=_maybe_str(task.get("channel_id")),
        metadata=metadata,
    )


def _maybe_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _message_source(value: object) -> MessageSource:
    if isinstance(value, MessageSource):
        return value
    try:
        return MessageSource(str(value or MessageSource.INTERNAL.value).strip().lower())
    except Exception:
        return MessageSource.INTERNAL
