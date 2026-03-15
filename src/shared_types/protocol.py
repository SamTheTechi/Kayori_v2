from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from shared_types.models import (
    LocationState,
    MessageEnvelope,
    MoodState,
    OutboundMessage,
)
from shared_types.types import (
    ScheduledTask,
    SchedulerBackend,
    ToolAuditEvent,
    Trigger,
)


@runtime_checkable
class MessageBus(Protocol):
    async def publish(self, envelope: MessageEnvelope) -> None: ...

    async def consume(self) -> MessageEnvelope: ...


@runtime_checkable
class InputAdapter(Protocol):
    name: str

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


@runtime_checkable
class OutputAdapter(Protocol):
    name: str

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def send(self, message: OutboundMessage) -> None: ...


@runtime_checkable
class StateStore(Protocol):
    async def get_mood(self) -> MoodState: ...

    async def set_mood(self, mood: MoodState) -> None: ...

    async def get_live_location(self) -> LocationState: ...

    async def set_live_location(self, location: LocationState) -> None: ...

    async def get_pinned_location(self) -> LocationState: ...

    async def set_pinned_location(self, location: LocationState) -> None: ...


#
# @runtime_checkable
# class MemoryConsolidator(Protocol):
#     async def consolidate(self, *, episode_limit: int) -> None:
#         ...

@runtime_checkable
class ToolAuditLogger(Protocol):
    async def log_tool_event(self, event: ToolAuditEvent) -> None: ...


@runtime_checkable
class EpisodicMemoryStore(Protocol):
    async def remember(
        self,
        *,
        fact: str,
        source: str,
        category: str = "misc",
        importance: int = 3,
        confidence: float = 0.8,
        tags: list[str] | None = None,
        context: str = "",
    ) -> Any: ...

    async def recall(
        self,
        query: str,
        limit: int = 3,
        *,
        min_score: float = 0.05,
    ) -> list[Any]: ...

    async def compact(self, *, max_episodes: int | None = None) -> int: ...


@runtime_checkable
class GraphMemoryStore(Protocol):
    async def remember(
        self,
        *,
        subject: str,
        predicate: str,
        obj: str,
        source: str,
        confidence: float = 0.8,
    ) -> Any: ...

    async def recall(
        self,
        *,
        entity: str | None = None,
        predicate: str | None = None,
        limit: int = 10,
    ) -> list[Any]: ...

    async def close(self) -> None: ...


@runtime_checkable
class SchedulerStore(Protocol):
    async def enqueue(self, task: ScheduledTask) -> str: ...

    async def pop_due(
        self, *, now_ts: float, limit: int = 100
    ) -> list[ScheduledTask]: ...

    async def get(self, task_id: str) -> ScheduledTask | None: ...


@runtime_checkable
class TriggerSchedulerBackend(SchedulerBackend, Protocol):
    async def push(self, trigger: Trigger) -> None: ...


__all__ = [
    # "CompanionStateStore",
    # "GoalTaskBrain",
    "InputAdapter",
    # "MemoryConsolidator",
    "MessageBus",
    "OutputAdapter",
    "EpisodicMemoryStore",
    "GraphMemoryStore",
    # "ProactiveKindStrategy",
    # "ProactiveMessagingPolicy",
    "SchedulerStore",
    "StateStore",
    "ToolAuditLogger",
    "TriggerSchedulerBackend",
]
