from __future__ import annotations

from typing import Any, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import Annotated

from shared_types.models import MessageEnvelope, MoodState, OutboundMessage


class GoalTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    due_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Goal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    priority: int = 3
    status: str = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompanionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inactivity_stage: str = "idle"
    resentment_score: float = 0.0
    last_proactive_message_at: str | None = None
    updated_at: str | None = None


class ProactiveKindPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    critical: bool = False


class ProactiveDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow: bool
    prompt: str | None = None
    reason: str
    stage: str
    resentment_score: float
    mark_proactive_sent: bool = False


class AgentGraphState(TypedDict, total=False):
    user_text: str
    thread_id: str
    mood: MoodState | None
    envelope: MessageEnvelope | None
    history: list[BaseMessage]
    messages: Annotated[list[BaseMessage], add_messages]
    reply_text: str
    error_reason: str | None


class PipelineState(TypedDict, total=False):
    envelope: MessageEnvelope
    mood: MoodState | None
    thread_id: str
    reply_text: str
    outbound: OutboundMessage | None


class ToolAuditEvent(TypedDict, total=False):
    timestamp: str
    event_type: Literal["tool_call", "tool_result", "tool_error"]
    thread_id: str
    source: str
    tool_name: str
    tool_input: Any


SchedulerMode = Literal["exact", "window"]


class ScheduleRequest(TypedDict, total=False):
    mode: SchedulerMode
    content: str
    source: str
    is_dm: bool
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
    source: str
    is_dm: bool
    target_user_id: str | None
    channel_id: str | None
    metadata: dict[str, Any]


__all__ = [
    "AgentGraphState",
    "CompanionState",
    "Goal",
    "GoalTask",
    "PipelineState",
    "ProactiveDecision",
    "ProactiveKindPlan",
    "ScheduleRequest",
    "ScheduledTask",
    "SchedulerMode",
    "ToolAuditEvent",
]
