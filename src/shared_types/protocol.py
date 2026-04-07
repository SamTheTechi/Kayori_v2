from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from langchain_core.messages import BaseMessage

from src.shared_types.models import (
    InteractionState,
    MessageEnvelope,
    LifeNote,
    MoodState,
    OutboundMessage,
)
from src.shared_types.models import MessagesHistory, MessageSource
from src.shared_types.types import Trigger


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
    route_source: MessageSource

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def send(self, message: OutboundMessage) -> None: ...


@runtime_checkable
class StateStore(Protocol):

    async def get_mood(self) -> MoodState: ...

    async def set_mood(self, mood: MoodState) -> None: ...

    async def get_history(self) -> MessagesHistory: ...

    async def append_messages(self, msgs: list[BaseMessage]) -> None: ...

    async def replace_messages(self, msgs: list[BaseMessage]) -> None: ...

    async def get_agent_context(self, n: int) -> list[BaseMessage]: ...

    async def get_mood_context(self, n: int) -> list[BaseMessage]: ...

    async def history_len(self) -> int: ...

    async def get_interaction_state(self) -> InteractionState: ...

    async def set_interaction_state(self, state: InteractionState) -> None: ...

    async def get_life_profile(self) -> str: ...

    async def replace_life_profile(self, profile: str) -> None: ...

    async def get_life_notes(self) -> list[LifeNote]: ...

    async def append_life_note(self, note: LifeNote) -> None: ...

    async def consume_life_note(self) -> LifeNote | None: ...

    async def prune_life_notes(self, *, max_age_seconds: float) -> int: ...

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

    async def compact(
        self,
        *,
        max_episodes: int | None = None,
    ) -> int: ...


class EpisodicMemoryBackendRecord:
    def __init__(
        self,
        *,
        id: str,
        content: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.id = id
        self.content = content
        self.metadata = dict(metadata or {})


class EpisodicMemorySearchResult:
    def __init__(
        self,
        *,
        record: EpisodicMemoryBackendRecord,
        backend_score: float,
    ) -> None:
        self.record = record
        self.backend_score = float(backend_score)


@runtime_checkable
class EpisodicMemoryBackend(Protocol):
    async def upsert(
        self,
        *,
        record_id: str,
        content: str,
        metadata: dict[str, Any],
        namespace: str | None = None,
    ) -> None: ...

    async def search(
        self,
        *,
        query: str,
        limit: int,
        namespace: str | None = None,
    ) -> list[EpisodicMemorySearchResult]: ...

    async def list_ids(
        self,
        *,
        namespace: str | None = None,
    ) -> list[str]: ...

    async def fetch_records(
        self,
        *,
        ids: list[str],
        namespace: str | None = None,
    ) -> list[EpisodicMemoryBackendRecord]: ...

    async def delete(
        self,
        *,
        ids: list[str],
        namespace: str | None = None,
    ) -> None: ...


@runtime_checkable
class SchedulerBackend(Protocol):
    async def push(self, trigger: Trigger) -> None: ...

    async def pop_due(self, now: float) -> list[Trigger]: ...

    async def reschedule(self, trigger: Trigger) -> None: ...

    async def suppress(self, trigger_id: str, until: float) -> None: ...

    async def remove(self, trigger_id: str) -> None: ...

    async def list_pending(self) -> list[Trigger]: ...

    async def restore(self) -> list[Trigger]: ...


__all__ = [
    "InputAdapter",
    "SchedulerBackend",
    "MessageBus",
    "OutputAdapter",
    "EpisodicMemoryBackend",
    "EpisodicMemoryBackendRecord",
    "EpisodicMemorySearchResult",
    "EpisodicMemoryStore",
    "StateStore",
]
