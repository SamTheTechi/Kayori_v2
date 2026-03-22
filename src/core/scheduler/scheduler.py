from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from datetime import datetime
from typing import Any, Callable, Coroutine

from redis.asyncio import Redis

from src.logger import get_logger
from src.shared_types.models import EMOTIONS, MessageEnvelope, MessageSource
from src.shared_types.protocol import MessageBus, StateStore
from src.shared_types.protocol import SchedulerBackend
from src.shared_types.thread_identity import resolve_thread_id
from src.shared_types.types import FiredTrigger, MissedPolicy, Trigger, TriggerType

logger = get_logger("core.scheduler")

TriggerHandler = Callable[[FiredTrigger], Coroutine[Any, Any, None]]

DEFAULT_MOOD_CHECK_INTERVAL = 60.0
DEFAULT_CURIOSITY_WINDOW_START = 9 * 60 * 60
DEFAULT_CURIOSITY_WINDOW_END = 21 * 60 * 60
DEFAULT_CURIOSITY_SLOTS = 3


class AgentScheduler:
    def __init__(
        self,
        backend: SchedulerBackend,
        *,
        bus: MessageBus | None = None,
        state_store: StateStore | None = None,
        tick_interval: float = 1.0,
        default_mood_check_interval: float = DEFAULT_MOOD_CHECK_INTERVAL,
    ) -> None:
        self._backend = backend
        self._bus = bus
        self._state_store = state_store
        self._tick = tick_interval
        self._default_mood_check_interval = default_mood_check_interval
        self._handlers: dict[TriggerType, list[TriggerHandler]] = {
            trigger_type: [] for trigger_type in TriggerType
        }
        self._running = False
        self._task: asyncio.Task[None] | None = None

    @classmethod
    def with_memory(
        cls,
        *,
        bus: MessageBus | None = None,
        state_store: StateStore | None = None,
        tick_interval: float = 1.0,
        default_mood_check_interval: float = DEFAULT_MOOD_CHECK_INTERVAL,
    ) -> "AgentScheduler":
        from src.core.scheduler.backend_memory import InMemoryBackend

        return cls(
            InMemoryBackend(),
            bus=bus,
            state_store=state_store,
            tick_interval=tick_interval,
            default_mood_check_interval=default_mood_check_interval,
        )

    @classmethod
    def with_redis(
        cls,
        *,
        redis_client: Redis,
        bus: MessageBus | None = None,
        state_store: StateStore | None = None,
        tick_interval: float = 1.0,
        default_mood_check_interval: float = DEFAULT_MOOD_CHECK_INTERVAL,
    ) -> "AgentScheduler":
        from src.core.scheduler.backend_redis import RedisBackend

        backend = RedisBackend(redis_client=redis_client)
        return cls(
            backend,
            bus=bus,
            state_store=state_store,
            tick_interval=tick_interval,
            default_mood_check_interval=default_mood_check_interval,
        )

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
        now = time.time()
        check_interval = float(
            trigger.check_interval_sec or self._default_mood_check_interval
        )

        if trigger.trigger_type == TriggerType.PRECISE:
            if trigger.fire_at is None:
                raise ValueError("precise triggers require fire_at")
            if trigger.repeat and trigger.repeat_interval_sec is None:
                raise ValueError(
                    "repeating precise triggers require repeat_interval_sec")
        elif trigger.trigger_type == TriggerType.FUZZY:
            if trigger.window_start_ts is None or trigger.window_end_ts is None:
                raise ValueError(
                    "fuzzy triggers require window_start_ts and window_end_ts")
            start = float(trigger.window_start_ts)
            end = float(trigger.window_end_ts)
            if end <= start:
                raise ValueError(
                    "fuzzy trigger window_end_ts must be after window_start_ts")
            if trigger.repeat and trigger.repeat_interval_sec is None:
                raise ValueError(
                    "repeating fuzzy triggers require repeat_interval_sec")
            if trigger.fire_at is None:
                trigger.fire_at = random.uniform(start, end)
            elif not start <= trigger.fire_at <= end:
                raise ValueError(
                    "fuzzy trigger fire_at must be inside the configured window")
        elif trigger.trigger_type == TriggerType.MOOD:
            if self._state_store is None:
                raise ValueError("mood triggers require state_store")
            if not trigger.mood_key:
                raise ValueError("mood triggers require mood_key")
            if trigger.mood_threshold is None:
                raise ValueError("mood triggers require mood_threshold")
            if trigger.mood_direction not in {"gte", "lte"}:
                raise ValueError(
                    "mood triggers require mood_direction to be 'gte' or 'lte'")
            if trigger.fire_at is None:
                trigger.fire_at = now + check_interval
        else:
            start_sec = (
                float(trigger.allowed_window_start_sec)
                if trigger.allowed_window_start_sec is not None
                else DEFAULT_CURIOSITY_WINDOW_START
            )
            end_sec = (
                float(trigger.allowed_window_end_sec)
                if trigger.allowed_window_end_sec is not None
                else DEFAULT_CURIOSITY_WINDOW_END
            )
            slot_count = trigger.target_slots_per_day or DEFAULT_CURIOSITY_SLOTS
            min_spacing = float(trigger.min_spacing_sec or 0.0)
            if end_sec <= start_sec:
                raise ValueError(
                    "curiosity allowed window end must be after start")
            if slot_count <= 0:
                raise ValueError(
                    "curiosity target_slots_per_day must be positive")
            if min_spacing > (end_sec - start_sec) / slot_count:
                raise ValueError(
                    "curiosity min_spacing_sec is too large for the window")
            if trigger.fire_at is None:
                search_from = now
                while True:
                    day_start = _start_of_day(search_from)
                    window_start = day_start + start_sec
                    window_end = day_start + end_sec
                    bucket_size = (window_end - window_start) / slot_count
                    wiggle = max(0.0, (bucket_size - min_spacing) / 2)
                    payload = json.dumps(
                        trigger.rule_metadata,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    seed_input = f"{trigger.trigger_id}:{int(day_start)}:{
                        payload}"
                    seed = int.from_bytes(
                        hashlib.sha256(seed_input.encode()).digest()[:8],
                        "big",
                    )
                    rng = random.Random(seed)
                    slots = []
                    for index in range(slot_count):
                        center = window_start + bucket_size * (index + 0.5)
                        slots.append(
                            center + (rng.uniform(-wiggle, wiggle) if wiggle else 0.0))
                    future_slots = [
                        slot for slot in slots if slot > search_from]
                    if future_slots:
                        trigger.fire_at = future_slots[0]
                        break
                    search_from = _start_of_next_day(search_from)

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

            next_fire_at: float | None = None
            check_interval = float(
                trigger.check_interval_sec or self._default_mood_check_interval
            )

            if trigger.trigger_type == TriggerType.MOOD:
                next_fire_at = now + check_interval
            elif trigger.trigger_type == TriggerType.PRECISE:
                if trigger.missed_policy == MissedPolicy.FIRE_IMMEDIATELY:
                    next_fire_at = now
                elif trigger.repeat and trigger.repeat_interval_sec is not None:
                    interval = float(trigger.repeat_interval_sec)
                    if interval <= 0:
                        raise ValueError(
                            "repeat_interval_sec must be positive")
                    steps = max(
                        1, int((now - float(trigger.fire_at)) // interval) + 1)
                    next_fire_at = float(trigger.fire_at) + steps * interval
            elif trigger.trigger_type == TriggerType.FUZZY:
                if trigger.repeat and trigger.repeat_interval_sec is not None:
                    start = float(trigger.window_start_ts or now)
                    end = float(trigger.window_end_ts or now)
                    interval = float(trigger.repeat_interval_sec)
                    cycles = max(1, int((now - start) // interval) + 1)
                    next_fire_at = random.uniform(
                        start + cycles * interval,
                        end + cycles * interval,
                    )
            elif trigger.repeat:
                start_sec = (
                    float(trigger.allowed_window_start_sec)
                    if trigger.allowed_window_start_sec is not None
                    else DEFAULT_CURIOSITY_WINDOW_START
                )
                end_sec = (
                    float(trigger.allowed_window_end_sec)
                    if trigger.allowed_window_end_sec is not None
                    else DEFAULT_CURIOSITY_WINDOW_END
                )
                slot_count = trigger.target_slots_per_day or DEFAULT_CURIOSITY_SLOTS
                min_spacing = float(trigger.min_spacing_sec or 0.0)
                search_from = now
                while True:
                    day_start = _start_of_day(search_from)
                    window_start = day_start + start_sec
                    window_end = day_start + end_sec
                    bucket_size = (window_end - window_start) / slot_count
                    wiggle = max(0.0, (bucket_size - min_spacing) / 2)
                    payload = json.dumps(
                        trigger.rule_metadata,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    seed_input = f"{trigger.trigger_id}:{int(day_start)}:{
                        payload}"
                    seed = int.from_bytes(
                        hashlib.sha256(seed_input.encode()).digest()[:8],
                        "big",
                    )
                    rng = random.Random(seed)
                    slots = []
                    for index in range(slot_count):
                        center = window_start + bucket_size * (index + 0.5)
                        slots.append(
                            center + (rng.uniform(-wiggle, wiggle) if wiggle else 0.0))
                    future_slots = [
                        slot for slot in slots if slot > search_from]
                    if future_slots:
                        next_fire_at = future_slots[0]
                        break
                    search_from = _start_of_next_day(search_from)

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
        mood_value: float | None = None
        next_fire_at: float | None = None
        should_publish = True

        if trigger.trigger_type == TriggerType.MOOD:
            state_store = self._state_store
            if state_store is None:
                raise ValueError("mood triggers require state_store")
            payload = trigger.payload
            mood = await state_store.get_mood(
                resolve_thread_id(
                    target_user_id=str(payload.get("target_user_id") or "").strip(),
                    channel_id=str(payload.get("channel_id") or "").strip(),
                    author_id=str(payload.get("author_id") or "").strip(),
                )
            )
            mood_keys = {key.lower(): key for key in EMOTIONS}
            mood_key = str(trigger.mood_key or "").strip().lower()
            if mood_key not in mood_keys:
                raise ValueError(f"unknown mood key: {trigger.mood_key}")
            mood_value = float(getattr(mood, mood_keys[mood_key]))
            threshold = float(trigger.mood_threshold or 0.0)
            direction = str(trigger.mood_direction or "gte")
            should_publish = (
                mood_value <= threshold if direction == "lte" else mood_value >= threshold
            )
            if not should_publish:
                next_fire_at = fired_at + float(
                    trigger.check_interval_sec or self._default_mood_check_interval
                )
        elif trigger.repeat:
            if trigger.trigger_type == TriggerType.PRECISE:
                next_fire_at = fired_at + \
                    float(trigger.repeat_interval_sec or 0.0)
            elif trigger.trigger_type == TriggerType.FUZZY:
                start = float(trigger.window_start_ts or 0.0)
                end = float(trigger.window_end_ts or 0.0)
                interval = float(trigger.repeat_interval_sec or 0.0)
                cycles = max(1, int((fired_at - start) // interval) + 1)
                next_fire_at = random.uniform(
                    start + cycles * interval,
                    end + cycles * interval,
                )
            else:
                start_sec = (
                    float(trigger.allowed_window_start_sec)
                    if trigger.allowed_window_start_sec is not None
                    else DEFAULT_CURIOSITY_WINDOW_START
                )
                end_sec = (
                    float(trigger.allowed_window_end_sec)
                    if trigger.allowed_window_end_sec is not None
                    else DEFAULT_CURIOSITY_WINDOW_END
                )
                slot_count = trigger.target_slots_per_day or DEFAULT_CURIOSITY_SLOTS
                min_spacing = float(trigger.min_spacing_sec or 0.0)
                search_from = fired_at
                while True:
                    day_start = _start_of_day(search_from)
                    window_start = day_start + start_sec
                    window_end = day_start + end_sec
                    bucket_size = (window_end - window_start) / slot_count
                    wiggle = max(0.0, (bucket_size - min_spacing) / 2)
                    payload = json.dumps(
                        trigger.rule_metadata,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    seed_input = f"{trigger.trigger_id}:{int(day_start)}:{
                        payload}"
                    seed = int.from_bytes(
                        hashlib.sha256(seed_input.encode()).digest()[:8],
                        "big",
                    )
                    rng = random.Random(seed)
                    slots = []
                    for index in range(slot_count):
                        center = window_start + bucket_size * (index + 0.5)
                        slots.append(
                            center + (rng.uniform(-wiggle, wiggle) if wiggle else 0.0))
                    future_slots = [
                        slot for slot in slots if slot > search_from]
                    if future_slots:
                        next_fire_at = future_slots[0]
                        break
                    search_from = _start_of_next_day(search_from)

        if should_publish:
            fired = FiredTrigger(
                trigger=trigger,
                fired_at=fired_at,
                was_late=fired_at > float(
                    trigger.fire_at or fired_at) + self._tick,
            )

            handlers = self._handlers.get(trigger.trigger_type) or []
            if handlers:
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
                                "trigger_id": trigger.trigger_id,
                                "trigger_type": trigger.trigger_type.value,
                            },
                            error=result,
                        )
            elif self._bus is None:
                await logger.warning(
                    "scheduler_trigger_unhandled",
                    "Scheduler trigger fired without handlers or bus.",
                    context={
                        "trigger_id": trigger.trigger_id,
                        "trigger_type": trigger.trigger_type.value,
                    },
                )

            if self._bus is not None:
                content = str(
                    trigger.payload.get(
                        "content") or trigger.payload.get("message") or ""
                ).strip()
                if not content:
                    await logger.warning(
                        "scheduler_trigger_dropped_empty_content",
                        "Dropped scheduler trigger with empty content.",
                        context={
                            "trigger_id": trigger.trigger_id,
                            "trigger_type": trigger.trigger_type.value,
                        },
                    )
                else:
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
                    if mood_value is not None:
                        metadata["scheduler_mood_value"] = mood_value
                        metadata["scheduler_mood_key"] = trigger.mood_key

                    await self._bus.publish(
                        MessageEnvelope(
                            source=MessageSource.SCHEDULER,
                            content=content,
                            channel_id=str(
                                trigger.payload.get(
                                    "channel_id") or "").strip(),
                            author_id=str(
                                trigger.payload.get(
                                    "author_id") or "").strip(),
                            message_id=str(
                                trigger.payload.get(
                                    "message_id") or "").strip(),
                            target_user_id=str(
                                trigger.payload.get(
                                    "target_user_id" or "").strip()
                            ),
                            metadata=metadata,
                        )
                    )

        if next_fire_at is None:
            await self._backend.remove(trigger.trigger_id)
            return

        trigger.fire_at = next_fire_at
        await self._backend.reschedule(trigger)
def _start_of_day(ts: float) -> float:
    dt = datetime.fromtimestamp(ts).astimezone()
    midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.timestamp()


def _start_of_next_day(ts: float) -> float:
    return _start_of_day(ts) + 24 * 60 * 60


TaskScheduler = AgentScheduler

__all__ = ["AgentScheduler", "TaskScheduler", "TriggerHandler"]
