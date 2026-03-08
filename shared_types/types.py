from __future__ import annotations

from typing import Any, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import Annotated

from shared_types.models import (
    MessageEnvelope,
    MessageSource,
    MoodState,
    OutboundMessage
)


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


__all__ = [
    "AgentGraphState",
    "ScheduleRequest",
    "ScheduledTask",
    "SchedulerMode",
    "ToolAuditEvent",
    "OutputSinkMode",
]
