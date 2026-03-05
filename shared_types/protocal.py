from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from shared_types.models import LocationState, MessageEnvelope, MoodState, OutboundMessage
from shared_types.types import (
    CompanionState,
    Goal,
    GoalTask,
    ProactiveDecision,
    ProactiveKindPlan,
    ScheduledTask,
    ToolAuditEvent,
)


@runtime_checkable
class MessageBus(Protocol):
    async def publish(self, envelope: MessageEnvelope) -> None:
        ...

    async def consume(self) -> MessageEnvelope:
        ...


@runtime_checkable
class InputAdapter(Protocol):
    name: str

    async def start(self) -> None:
        ...

    async def stop(self) -> None:
        ...


@runtime_checkable
class OutputAdapter(Protocol):
    name: str

    async def start(self) -> None:
        ...

    async def stop(self) -> None:
        ...

    async def send(self, message: OutboundMessage) -> None:
        ...


@runtime_checkable
class StateStore(Protocol):
    async def get_mood(self) -> MoodState:
        ...

    async def set_mood(self, mood: MoodState) -> None:
        ...

    async def get_live_location(self) -> LocationState:
        ...

    async def set_live_location(self, location: LocationState) -> None:
        ...

    async def get_pinned_location(self) -> LocationState:
        ...

    async def set_pinned_location(self, location: LocationState) -> None:
        ...


@runtime_checkable
class MemoryConsolidator(Protocol):
    async def consolidate(self, *, episode_limit: int) -> None:
        ...


@runtime_checkable
class GoalTaskBrain(Protocol):
    async def due_tasks(self, *, within_minutes: int) -> list[GoalTask]:
        ...

    async def mark_notified(self, task_id: str) -> None:
        ...

    async def list_goals(self, *, status: str, limit: int = 5) -> list[Goal]:
        ...

    async def next_actions(self, *, limit: int = 5) -> list[GoalTask]:
        ...


@runtime_checkable
class CompanionStateStore(Protocol):
    async def get_state(self) -> CompanionState:
        ...

    async def set_state(self, state: CompanionState) -> None:
        ...


@runtime_checkable
class ProactiveMessagingPolicy(Protocol):
    def decide(
        self,
        *,
        kind: str,
        base_prompt: str,
        state: CompanionState,
        now_iso: str,
        critical: bool = False,
    ) -> ProactiveDecision:
        ...


@runtime_checkable
class ProactiveKindStrategy(Protocol):
    def next_kind(
        self,
        *,
        state: CompanionState,
        now_iso: str,
    ) -> ProactiveKindPlan | None:
        ...


@runtime_checkable
class ToolAuditLogger(Protocol):
    async def log_tool_event(self, event: ToolAuditEvent) -> None:
        ...


@runtime_checkable
class EpisodicMemoryStore(Protocol):
    async def remember(
        self,
        *,
        event: str,
        source: str,
        salience: int = 3,
        emotion: str = "Neutral",
        tags: list[str] | None = None,
        context: str = "",
    ) -> Any:
        ...

    async def recall(
        self,
        query: str,
        limit: int = 3,
        *,
        min_score: float = 0.05,
    ) -> list[Any]:
        ...

    async def recent(self, limit: int = 5) -> list[Any]:
        ...

    async def compact(self, *, max_episodes: int | None = None) -> int:
        ...


@runtime_checkable
class SchedulerStore(Protocol):
    async def enqueue(self, task: ScheduledTask) -> str:
        ...

    async def pop_due(self, *, now_ts: float, limit: int = 100) -> list[ScheduledTask]:
        ...

    async def get(self, task_id: str) -> ScheduledTask | None:
        ...


__all__ = [
    "CompanionStateStore",
    "GoalTaskBrain",
    "InputAdapter",
    "MemoryConsolidator",
    "MessageBus",
    "OutputAdapter",
    "EpisodicMemoryStore",
    "ProactiveKindStrategy",
    "ProactiveMessagingPolicy",
    "SchedulerStore",
    "StateStore",
    "ToolAuditLogger",
]
