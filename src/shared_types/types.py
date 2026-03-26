from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Annotated, Literal, TypedDict
from uuid import uuid4

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from src.shared_types.models import MessageEnvelope, MessageSource, MoodState


class AgentGraphState(TypedDict, total=False):
    content: str
    messages: Annotated[list[BaseMessage], add_messages]
    mood: MoodState | None
    episodic: list[dict[str, Any]]
    envelope: MessageEnvelope
    reply_text: str
    error_reason: str | None


class LifeGraphState(TypedDict, total=False):
    content: str
    messages: Annotated[list[BaseMessage], add_messages]
    episodic: list[dict[str, Any]]
    life_profile: str
    life_notes: list[str]
    notes: list[str]
    error_reason: str | None


OutputSinkMode = Literal["direct", "multi"]


class TriggerType(str, Enum):
    FUZZY = "fuzzy"
    PRECISE = "precise"


@dataclass(slots=True)
class Trigger:
    trigger_type: TriggerType
    source: MessageSource
    interval_seconds: float
    content: str = "__internal__"
    metadata: dict[str, Any] = field(default_factory=dict)
    repeat: bool = False
    fuzzy_seconds: float | None = None
    _trigger_id: str = field(default_factory=lambda: uuid4().hex, repr=False)
    _scheduled_for: float | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger_type": self.trigger_type.value,
            "source": self.source.value,
            "content": self.content,
            "metadata": self.metadata,
            "interval_seconds": self.interval_seconds,
            "repeat": self.repeat,
            "fuzzy_seconds": self.fuzzy_seconds,
            "_trigger_id": self._trigger_id,
            "_scheduled_for": self._scheduled_for,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Trigger":
        return cls(
            trigger_type=TriggerType(str(data["trigger_type"])),
            source=MessageSource(str(data["source"])),
            content=str(data.get("content") or "").strip(),
            metadata=dict(data.get("metadata") or {}),
            interval_seconds=float(data.get("interval_seconds") or 0.0),
            repeat=bool(data.get("repeat", False)),
            fuzzy_seconds=_optional_float(data.get("fuzzy_seconds")),
            _trigger_id=str(data.get("_trigger_id") or uuid4().hex),
            _scheduled_for=_optional_float(data.get("_scheduled_for")),
        )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


__all__ = [
    "AgentGraphState",
    "LifeGraphState",
    "OutputSinkMode",
    "Trigger",
    "TriggerType",
]
