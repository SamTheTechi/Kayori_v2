from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated, Any, Literal, Protocol, TypedDict, runtime_checkable

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from shared_types.models import MessageEnvelope, MessageSource, MoodState


class AgentGraphState(TypedDict, total=False):
    user_text: str
    thread_id: str
    mood: MoodState | None
    envelope: MessageEnvelope | None
    history: list[BaseMessage]
    messages: Annotated[list[BaseMessage], add_messages]
    reply_text: str
    error_reason: str | None


class ToolAuditEvent(TypedDict, total=False):
    timestamp: str
    event_type: Literal["tool_call", "tool_result", "tool_error"]
    thread_id: str
    source: str
    tool_name: str
    tool_input: Any


SchedulerMode = Literal["exact", "window"]
OutputSinkMode = Literal["direct", "multi"]
MoodDirection = Literal["gte", "lte"]


class ScheduleRequest(TypedDict, total=False):
    mode: SchedulerMode
    content: str
    source: MessageSource | str
    target_user_id: str | None
    channel_id: str | None
    metadata: dict[str, Any]
    run_at: str | float | int
    window_start: str | float | int
    window_end: str | float | int


class ScheduledTask(TypedDict, total=False):
    id: str
    mode: SchedulerMode
    due_ts: float
    created_at: str
    content: str
    source: MessageSource | str
    target_user_id: str | None
    channel_id: str | None
    metadata: dict[str, Any]


class TriggerType(str, Enum):
    FUZZY = "fuzzy"
    PRECISE = "precise"
    MOOD = "mood"
    CURIOSITY = "curiosity"


class MissedPolicy(str, Enum):
    FIRE_IMMEDIATELY = "fire_immediately"
    SKIP_RESCHEDULE = "skip_reschedule"
    RECHECK = "recheck"


@dataclass(slots=True)
class Trigger:
    trigger_type: TriggerType
    payload: dict[str, Any] = field(default_factory=dict)
    trigger_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    fire_at: float | None = None
    repeat: bool = False
    repeat_interval_sec: float | None = None
    check_interval_sec: float | None = None
    missed_policy: MissedPolicy = MissedPolicy.SKIP_RESCHEDULE
    window_start_ts: float | None = None
    window_end_ts: float | None = None
    mood_key: str | None = None
    mood_threshold: float | None = None
    mood_direction: MoodDirection | None = None
    allowed_window_start_sec: float | None = None
    allowed_window_end_sec: float | None = None
    target_slots_per_day: int | None = None
    min_spacing_sec: float | None = None
    rule_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger_type": self.trigger_type.value,
            "payload": self.payload,
            "trigger_id": self.trigger_id,
            "fire_at": self.fire_at,
            "repeat": self.repeat,
            "repeat_interval_sec": self.repeat_interval_sec,
            "check_interval_sec": self.check_interval_sec,
            "missed_policy": self.missed_policy.value,
            "window_start_ts": self.window_start_ts,
            "window_end_ts": self.window_end_ts,
            "mood_key": self.mood_key,
            "mood_threshold": self.mood_threshold,
            "mood_direction": self.mood_direction,
            "allowed_window_start_sec": self.allowed_window_start_sec,
            "allowed_window_end_sec": self.allowed_window_end_sec,
            "target_slots_per_day": self.target_slots_per_day,
            "min_spacing_sec": self.min_spacing_sec,
            "rule_metadata": self.rule_metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Trigger":
        return cls(
            trigger_type=TriggerType(str(data["trigger_type"])),
            payload=dict(data.get("payload") or {}),
            trigger_id=str(data.get("trigger_id") or uuid.uuid4()),
            fire_at=_optional_float(data.get("fire_at")),
            repeat=bool(data.get("repeat", False)),
            repeat_interval_sec=_optional_float(data.get("repeat_interval_sec")),
            check_interval_sec=_optional_float(data.get("check_interval_sec")),
            missed_policy=MissedPolicy(
                str(data.get("missed_policy") or MissedPolicy.SKIP_RESCHEDULE.value)
            ),
            window_start_ts=_optional_float(data.get("window_start_ts")),
            window_end_ts=_optional_float(data.get("window_end_ts")),
            mood_key=_optional_str(data.get("mood_key")),
            mood_threshold=_optional_float(data.get("mood_threshold")),
            mood_direction=_optional_direction(data.get("mood_direction")),
            allowed_window_start_sec=_optional_float(
                data.get("allowed_window_start_sec")
            ),
            allowed_window_end_sec=_optional_float(data.get("allowed_window_end_sec")),
            target_slots_per_day=_optional_int(data.get("target_slots_per_day")),
            min_spacing_sec=_optional_float(data.get("min_spacing_sec")),
            rule_metadata=dict(data.get("rule_metadata") or {}),
        )


@dataclass(slots=True)
class FiredTrigger:
    trigger: Trigger
    fired_at: float
    was_late: bool


@runtime_checkable
class SchedulerBackend(Protocol):
    async def push(self, trigger: Trigger) -> None: ...

    async def pop_due(self, now: float) -> list[Trigger]: ...

    async def reschedule(self, trigger: Trigger) -> None: ...

    async def suppress(self, trigger_id: str, until: float) -> None: ...

    async def remove(self, trigger_id: str) -> None: ...

    async def list_pending(self) -> list[Trigger]: ...

    async def restore(self) -> list[Trigger]: ...

    async def close(self) -> None: ...


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_direction(value: Any) -> MoodDirection | None:
    text = _optional_str(value)
    if text not in {"gte", "lte"}:
        return None
    return text


__all__ = [
    "AgentGraphState",
    "FiredTrigger",
    "MissedPolicy",
    "MoodDirection",
    "OutputSinkMode",
    "ScheduleRequest",
    "ScheduledTask",
    "SchedulerBackend",
    "SchedulerMode",
    "ToolAuditEvent",
    "Trigger",
    "TriggerType",
]
