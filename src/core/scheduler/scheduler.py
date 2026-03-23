from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from datetime import datetime
from typing import Any, Callable, Coroutine

from src.logger import get_logger
from src.shared_types.models import MessageEnvelope, MessageSource
from src.shared_types.protocol import MessageBus, SchedulerBackend
from src.shared_types.types import FiredTrigger, MissedPolicy, Trigger, TriggerType

logger = get_logger("core.scheduler")

TriggerHandler = Callable[[FiredTrigger], Coroutine[Any, Any, None]]

DEFAULT_LIFE_WINDOW_START = 9 * 60 * 60
DEFAULT_LIFE_WINDOW_END = 21 * 60 * 60
DEFAULT_LIFE_SLOTS = 3


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
        self._handlers: dict[TriggerType, list[TriggerHandler]] = {
            trigger_type: [] for trigger_type in TriggerType
        }
        self._running = False
        self._task: asyncio.Task[None] | None = None

    def register_handler(
        self,
        trigger_type: TriggerType,
        handler: TriggerHandler,
    ) -> None:
        self._handlers[trigger_type].append(handler)

    def on(self, trigger_type: TriggerType) -> Callable[[TriggerHandler], TriggerHandler]:
        def decorator(handler: TriggerHandler) -> TriggerHandler:
            self.register_handler(trigger_type, handler)
            return handler

        return decorator

    async def push(self, trigger: Trigger) -> None:
        _normalize_trigger(trigger, now=time.time())
        await self._backend.push(trigger)
        await logger.debug(
            "scheduler_trigger_pushed",
            "Scheduled trigger.",
            context={
                "trigger_id": trigger.trigger_id,
                "trigger_type": trigger.trigger_type.value,
                "fire_at": trigger.fire_at,
            },
        )

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
            if trigger.fire_at is None or trigger.fire_at >= now:
                continue

            next_fire_at = _compute_missed_fire_at(trigger, now)
            await self._backend.remove(trigger.trigger_id)
            if next_fire_at is not None:
                trigger.fire_at = next_fire_at
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
                await logger.exception(
                    "scheduler_loop_failed",
                    "Scheduler loop failed.",
                    error=exc,
                )
            await asyncio.sleep(self._tick)

    async def _dispatch(self, trigger: Trigger, fired_at: float) -> None:
        fired = FiredTrigger(
            trigger=trigger,
            fired_at=fired_at,
            was_late=fired_at > float(trigger.fire_at or fired_at) + self._tick,
        )

        await self._run_handlers(fired)
        await self._publish_to_bus(trigger, fired_at)

        next_fire_at = _compute_repeat_fire_at(trigger, fired_at)
        if next_fire_at is None:
            await self._backend.remove(trigger.trigger_id)
            return

        trigger.fire_at = next_fire_at
        await self._backend.reschedule(trigger)

    async def _run_handlers(self, fired: FiredTrigger) -> None:
        handlers = self._handlers.get(fired.trigger.trigger_type) or []
        if not handlers:
            if self._bus is None:
                await logger.warning(
                    "scheduler_trigger_unhandled",
                    "Scheduler trigger fired without handlers or bus.",
                    context={
                        "trigger_id": fired.trigger.trigger_id,
                        "trigger_type": fired.trigger.trigger_type.value,
                    },
                )
            return

        results = await asyncio.gather(
            *(handler(fired) for handler in handlers),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                await logger.exception(
                    "scheduler_handler_failed",
                    "Scheduler handler failed.",
                    context={
                        "trigger_id": fired.trigger.trigger_id,
                        "trigger_type": fired.trigger.trigger_type.value,
                    },
                    error=result,
                )

    async def _publish_to_bus(self, trigger: Trigger, fired_at: float) -> None:
        if self._bus is None:
            return

        content = _extract_content(trigger)
        if not content:
            await logger.warning(
                "scheduler_trigger_dropped_empty_content",
                "Dropped scheduler trigger with empty content.",
                context={
                    "trigger_id": trigger.trigger_id,
                    "trigger_type": trigger.trigger_type.value,
                },
            )
            return

        await self._bus.publish(_build_envelope(trigger, fired_at, content))


def _normalize_trigger(trigger: Trigger, *, now: float) -> None:
    if trigger.trigger_type == TriggerType.PRECISE:
        if trigger.fire_at is not None and trigger.delay_seconds is not None:
            raise ValueError("precise triggers cannot use both fire_at and delay_seconds")
        if trigger.fire_at is None and trigger.delay_seconds is not None:
            if trigger.delay_seconds < 0:
                raise ValueError("delay_seconds must be non-negative")
            trigger.fire_at = now + float(trigger.delay_seconds)
        if trigger.fire_at is None:
            raise ValueError("precise triggers require fire_at or delay_seconds")
        if trigger.repeat and trigger.repeat_interval_sec is None:
            raise ValueError("repeating precise triggers require repeat_interval_sec")
        return

    if trigger.trigger_type == TriggerType.FUZZY:
        start = _require_float(trigger.window_start_ts, "fuzzy triggers require window_start_ts and window_end_ts")
        end = _require_float(trigger.window_end_ts, "fuzzy triggers require window_start_ts and window_end_ts")
        if end <= start:
            raise ValueError("fuzzy trigger window_end_ts must be after window_start_ts")
        if trigger.repeat and trigger.repeat_interval_sec is None:
            raise ValueError("repeating fuzzy triggers require repeat_interval_sec")
        if trigger.fire_at is None:
            trigger.fire_at = random.uniform(start, end)
        elif not start <= trigger.fire_at <= end:
            raise ValueError("fuzzy trigger fire_at must be inside the configured window")
        return

    _validate_life_trigger(trigger)
    if trigger.fire_at is None:
        trigger.fire_at = _compute_life_fire_at(trigger, after_ts=now)


def _compute_missed_fire_at(trigger: Trigger, now: float) -> float | None:
    if trigger.trigger_type == TriggerType.PRECISE:
        if trigger.missed_policy == MissedPolicy.FIRE_IMMEDIATELY:
            return now
        if not trigger.repeat or trigger.repeat_interval_sec is None:
            return None
        interval = float(trigger.repeat_interval_sec)
        if interval <= 0:
            raise ValueError("repeat_interval_sec must be positive")
        assert trigger.fire_at is not None
        steps = max(1, int((now - trigger.fire_at) // interval) + 1)
        return trigger.fire_at + steps * interval

    if trigger.trigger_type == TriggerType.FUZZY:
        if not trigger.repeat or trigger.repeat_interval_sec is None:
            return None
        start = float(trigger.window_start_ts or now)
        end = float(trigger.window_end_ts or now)
        interval = float(trigger.repeat_interval_sec)
        cycles = max(1, int((now - start) // interval) + 1)
        return random.uniform(start + cycles * interval, end + cycles * interval)

    if not trigger.repeat:
        return None
    return _compute_life_fire_at(trigger, after_ts=now)


def _compute_repeat_fire_at(trigger: Trigger, fired_at: float) -> float | None:
    if not trigger.repeat:
        return None

    if trigger.trigger_type == TriggerType.PRECISE:
        return fired_at + float(trigger.repeat_interval_sec or 0.0)

    if trigger.trigger_type == TriggerType.FUZZY:
        start = float(trigger.window_start_ts or 0.0)
        end = float(trigger.window_end_ts or 0.0)
        interval = float(trigger.repeat_interval_sec or 0.0)
        cycles = max(1, int((fired_at - start) // interval) + 1)
        return random.uniform(start + cycles * interval, end + cycles * interval)

    return _compute_life_fire_at(trigger, after_ts=fired_at)


def _validate_life_trigger(trigger: Trigger) -> None:
    start_sec, end_sec, slot_count, min_spacing = _life_config(trigger)
    if end_sec <= start_sec:
        raise ValueError("life allowed window end must be after start")
    if slot_count <= 0:
        raise ValueError("life target_slots_per_day must be positive")
    if min_spacing > (end_sec - start_sec) / slot_count:
        raise ValueError("life min_spacing_sec is too large for the window")


def _life_config(trigger: Trigger) -> tuple[float, float, int, float]:
    start_sec = (
        float(trigger.allowed_window_start_sec)
        if trigger.allowed_window_start_sec is not None
        else DEFAULT_LIFE_WINDOW_START
    )
    end_sec = (
        float(trigger.allowed_window_end_sec)
        if trigger.allowed_window_end_sec is not None
        else DEFAULT_LIFE_WINDOW_END
    )
    slot_count = trigger.target_slots_per_day or DEFAULT_LIFE_SLOTS
    min_spacing = float(trigger.min_spacing_sec or 0.0)
    return start_sec, end_sec, slot_count, min_spacing


def _compute_life_fire_at(trigger: Trigger, *, after_ts: float) -> float:
    start_sec, end_sec, slot_count, min_spacing = _life_config(trigger)
    search_from = after_ts

    while True:
        day_start = _start_of_day(search_from)
        window_start = day_start + start_sec
        window_end = day_start + end_sec
        bucket_size = (window_end - window_start) / slot_count
        wiggle = max(0.0, (bucket_size - min_spacing) / 2)
        seed = _life_seed(trigger, day_start)
        rng = random.Random(seed)

        slots = []
        for index in range(slot_count):
            center = window_start + bucket_size * (index + 0.5)
            offset = rng.uniform(-wiggle, wiggle) if wiggle else 0.0
            slots.append(center + offset)

        future_slots = [slot for slot in slots if slot > search_from]
        if future_slots:
            return future_slots[0]
        search_from = _start_of_next_day(search_from)


def _life_seed(trigger: Trigger, day_start: float) -> int:
    payload = json.dumps(
        trigger.rule_metadata,
        sort_keys=True,
        separators=(",", ":"),
    )
    seed_input = f"{trigger.trigger_id}:{int(day_start)}:{payload}"
    return int.from_bytes(hashlib.sha256(seed_input.encode()).digest()[:8], "big")


def _extract_content(trigger: Trigger) -> str:
    return str(trigger.payload.get("content") or trigger.payload.get("message") or "").strip()


def _build_envelope(trigger: Trigger, fired_at: float, content: str) -> MessageEnvelope:
    metadata = dict(trigger.payload.get("metadata") or {})
    metadata.update(
        {
            "scheduler_trigger_id": trigger.trigger_id,
            "scheduler_trigger_type": trigger.trigger_type.value,
            "scheduler_scheduled_for": trigger.fire_at,
            "scheduler_fired_at": fired_at,
            "scheduler_repeat": trigger.repeat,
            "scheduler_missed_policy": trigger.missed_policy.value,
        }
    )

    return MessageEnvelope(
        source=_message_source_for_trigger(trigger),
        content=content,
        channel_id=_optional_payload_text(trigger.payload, "channel_id"),
        author_id=_optional_payload_text(trigger.payload, "author_id"),
        message_id=_optional_payload_text(trigger.payload, "message_id"),
        target_user_id=_optional_payload_text(trigger.payload, "target_user_id"),
        metadata=metadata,
    )


def _message_source_for_trigger(trigger: Trigger) -> MessageSource:
    if trigger.trigger_type == TriggerType.LIFE:
        return MessageSource.LIFE
    return MessageSource.SCHEDULER


def _optional_payload_text(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_float(value: float | None, error_message: str) -> float:
    if value is None:
        raise ValueError(error_message)
    return float(value)


def _start_of_day(ts: float) -> float:
    dt = datetime.fromtimestamp(ts).astimezone()
    midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.timestamp()


def _start_of_next_day(ts: float) -> float:
    return _start_of_day(ts) + 24 * 60 * 60


__all__ = ["AgentScheduler", "TriggerHandler"]
