from __future__ import annotations

import asyncio
import random
import time

from src.logger import get_logger
from src.shared_types.models import MessageEnvelope
from src.shared_types.protocol import MessageBus, SchedulerBackend
from src.shared_types.types import Trigger, TriggerType

logger = get_logger("core.scheduler")


class AgentScheduler:
    def __init__(
        self,
        backend: SchedulerBackend,
        *,
        bus: MessageBus | None = None,
        tick_interval: float = 1.0,
    ) -> None:
        self._backend = backend
        self._bus = bus
        self._tick = tick_interval
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def push(self, trigger: Trigger) -> None:
        try:
            _normalize_trigger(trigger, now=time.time())
        except ValueError as exc:
            await logger.warning(
                "scheduler_trigger_rejected",
                "Rejected invalid scheduler trigger.",
                context={
                    "trigger_id": trigger._trigger_id,
                    "trigger_type": trigger.trigger_type.value,
                    "source": trigger.source.value,
                    "reason": str(exc),
                },
            )
            return
        await self._backend.push(trigger)

    async def remove(self, trigger_id: str) -> None:
        await self._backend.remove(trigger_id)

    async def suppress(self, trigger_id: str, until: float) -> None:
        await self._backend.suppress(trigger_id, until)

    async def list_pending(self) -> list[Trigger]:
        return await self._backend.list_pending()

    async def start(self) -> None:
        if self._running:
            return

        now = time.time()
        for trigger in await self._backend.restore():
            if trigger._scheduled_for is None or trigger._scheduled_for >= now:
                continue

            next_fire_at = _compute_restart_fire_at(trigger, now)
            await self._backend.remove(trigger._trigger_id)
            if next_fire_at is not None:
                trigger._scheduled_for = next_fire_at
                await self._backend.push(trigger)

        self._running = True
        self._task = asyncio.create_task(self._loop(), name="scheduler-loop")
        await logger.info(
            "scheduler_started",
            "Scheduler started.",
            context={"backend": type(self._backend).__name__},
        )

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        await logger.info("scheduler_stopped", "Scheduler stopped.")

    async def __aenter__(self) -> "AgentScheduler":
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.stop()

    async def _loop(self) -> None:
        while self._running:
            try:
                now = time.time()
                for trigger in await self._backend.pop_due(now):
                    asyncio.create_task(self._dispatch(trigger, now))
            except Exception as exc:
                await logger.error(
                    "scheduler_failed",
                    "Scheduler loop failed.",
                    error=exc,
                )
            await asyncio.sleep(self._tick)

    async def _dispatch(self, trigger: Trigger, fired_at: float) -> None:
        await self._publish_to_bus(trigger)

        next_fire_at = _compute_repeat_fire_at(trigger)
        if next_fire_at is None:
            await self._backend.remove(trigger._trigger_id)
            return

        trigger._scheduled_for = next_fire_at
        await self._backend.reschedule(trigger)

    async def _publish_to_bus(self, trigger: Trigger) -> None:
        if self._bus is None:
            await logger.warning(
                "scheduler_trigger_unhandled",
                "Scheduler trigger fired without a bus.",
                context={
                    "trigger_id": trigger._trigger_id,
                    "trigger_type": trigger.trigger_type.value,
                },
            )
            return

        content = trigger.content.strip()
        if not content:
            await logger.warning(
                "scheduler_trigger_dropped_empty_content",
                "Dropped scheduler trigger with empty content.",
                context={
                    "trigger_id": trigger._trigger_id,
                    "trigger_type": trigger.trigger_type.value,
                },
            )
            return

        await self._bus.publish(_build_envelope(trigger, content))


def _normalize_trigger(trigger: Trigger, *, now: float) -> None:
    _validate_trigger(trigger)
    trigger.content = trigger.content.strip()
    trigger._scheduled_for = _resolve_fire_at(
        trigger,
        now + trigger.interval_seconds,
    )


def _compute_restart_fire_at(trigger: Trigger, now: float) -> float | None:
    if not trigger.repeat:
        return now

    scheduled_at = trigger._scheduled_for or now
    next_base = scheduled_at
    while next_base < now:
        next_base += trigger.interval_seconds
    return _resolve_fire_at(trigger, next_base)


def _compute_repeat_fire_at(trigger: Trigger) -> float | None:
    if not trigger.repeat:
        return None

    base_time = (trigger._scheduled_for or 0.0) + trigger.interval_seconds
    return _resolve_fire_at(trigger, base_time)


def _validate_trigger(trigger: Trigger) -> None:
    if trigger.interval_seconds < 0:
        raise ValueError("interval_seconds must be non-negative")
    if trigger.repeat and trigger.interval_seconds <= 0:
        raise ValueError("repeating triggers require interval_seconds > 0")
    if trigger.fuzzy_seconds is not None and trigger.fuzzy_seconds < 0:
        raise ValueError("fuzzy_seconds must be non-negative")
    if trigger.trigger_type == TriggerType.FUZZY and trigger.fuzzy_seconds is None:
        raise ValueError("fuzzy triggers require fuzzy_seconds")
    if trigger.trigger_type != TriggerType.FUZZY and trigger.fuzzy_seconds is not None:
        raise ValueError("only fuzzy triggers may set fuzzy_seconds")


def _resolve_fire_at(trigger: Trigger, base_time: float) -> float:
    if trigger.trigger_type != TriggerType.FUZZY:
        return base_time
    return random.uniform(base_time, base_time + (trigger.fuzzy_seconds or 0.0))


def _build_envelope(trigger: Trigger, content: str) -> MessageEnvelope:
    return MessageEnvelope(
        source=trigger.source,
        content=content,
        metadata={
            **trigger.metadata,
            "scheduler_trigger_id": trigger._trigger_id,
            "scheduler_scheduled_for": trigger._scheduled_for,
            "scheduler_repeat": trigger.repeat,
        },
    )


__all__ = ["AgentScheduler"]
