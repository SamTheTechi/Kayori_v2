from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


from src.shared_types.models import MessageSource, MoodState, MessageEnvelope


class AgentGraphState(TypedDict, total=False):
    content: str
    messages: Annotated[list[BaseMessage], add_messages]
    mood: MoodState | None
    envelope: MessageEnvelope
    reply_text: str
    error_reason: str | None


OutputSinkMode = Literal["direct", "multi"]
class TriggerType(str, Enum):
    FUZZY = "fuzzy"
    PRECISE = "precise"
    LIFE = "life"


class MissedPolicy(str, Enum):
    FIRE_IMMEDIATELY = "fire_immediately"
    SKIP_RESCHEDULE = "skip_reschedule"


@dataclass(slots=True)
class Trigger:
    trigger_type: TriggerType
    payload: dict[str, Any] = field(default_factory=dict)
    trigger_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    fire_at: float | None = None
    delay_seconds: float | None = None
    repeat: bool = False
    repeat_interval_sec: float | None = None
    missed_policy: MissedPolicy = MissedPolicy.SKIP_RESCHEDULE
    window_start_ts: float | None = None
    window_end_ts: float | None = None
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
            "delay_seconds": self.delay_seconds,
            "repeat": self.repeat,
            "repeat_interval_sec": self.repeat_interval_sec,
            "missed_policy": self.missed_policy.value,
            "window_start_ts": self.window_start_ts,
            "window_end_ts": self.window_end_ts,
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
            delay_seconds=_optional_float(data.get("delay_seconds")),
            repeat=bool(data.get("repeat", False)),
            repeat_interval_sec=_optional_float(
                data.get("repeat_interval_sec")),
            missed_policy=MissedPolicy(
                str(data.get("missed_policy")
                    or MissedPolicy.SKIP_RESCHEDULE.value)
            ),
            window_start_ts=_optional_float(data.get("window_start_ts")),
            window_end_ts=_optional_float(data.get("window_end_ts")),
            allowed_window_start_sec=_optional_float(
                data.get("allowed_window_start_sec")
            ),
            allowed_window_end_sec=_optional_float(
                data.get("allowed_window_end_sec")),
            target_slots_per_day=_optional_int(
                data.get("target_slots_per_day")),
            min_spacing_sec=_optional_float(data.get("min_spacing_sec")),
            rule_metadata=dict(data.get("rule_metadata") or {}),
        )


@dataclass(slots=True)
class FiredTrigger:
    trigger: Trigger
    fired_at: float
    was_late: bool


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
__all__ = [
    "AgentGraphState",
    "FiredTrigger",
    "MissedPolicy",
    "OutputSinkMode",
    "Trigger",
    "TriggerType",
]
