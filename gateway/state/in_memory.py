from __future__ import annotations

import asyncio
from langchain_core.messages import BaseMessage
from datetime import UTC, datetime

from shared_types.models import InteractionState, LifeNote, MoodState, MessagesHistory, Todo


class InMemoryStateStore:
    def __init__(self) -> None:
        self._mood = MoodState()
        self._history = MessagesHistory()
        self._interaction_state = InteractionState()
        self._life_profile = ""
        self._life_notes: list[LifeNote] = []
        self._todos: list[Todo] = []
        self._lock = asyncio.Lock()
        # now = time.time()
        # self._live = LocationState(latitude=0.0, longitude=0.0, timestamp=now)
        # self._pinned = LocationState(
        #     latitude=0.0, longitude=0.0, timestamp=now)

    # ------------------------------------------------------------------
    # Mood
    # ------------------------------------------------------------------

    async def get_mood(self) -> MoodState:
        async with self._lock:
            return MoodState.from_dict(self._mood.as_dict())

    async def set_mood(self, mood: MoodState) -> None:
        async with self._lock:
            self._mood = MoodState.from_dict(mood.as_dict()).clamp()

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    async def get_history(self) -> MessagesHistory:
        async with self._lock:
            return MessagesHistory.from_dict(self._history.as_dict())

    async def append_messages(self, msgs: list[BaseMessage]) -> None:
        async with self._lock:
            self._history.append(msgs)

    async def replace_messages(self, msgs: list[BaseMessage]) -> None:
        """Called after compression to swap trimmed window back in."""
        async with self._lock:
            self._history.replace(msgs)

    async def get_agent_context(self, n: int) -> list[BaseMessage]:
        async with self._lock:
            return _agent_context(self._history.all(), n)

    async def get_mood_context(self, n: int) -> list[BaseMessage]:
        async with self._lock:
            return _raw_window(self._history.all(), n)

    async def history_len(self) -> int:
        async with self._lock:
            return len(self._history)

    async def get_interaction_state(self) -> InteractionState:
        async with self._lock:
            return InteractionState.from_dict(self._interaction_state.as_dict())

    async def set_interaction_state(self, state: InteractionState) -> None:
        async with self._lock:
            self._interaction_state = InteractionState.from_dict(state.as_dict())

    async def get_life_profile(self) -> str:
        async with self._lock:
            return str(self._life_profile)

    async def replace_life_profile(self, profile: str) -> None:
        async with self._lock:
            self._life_profile = _clean_profile(profile)

    async def get_life_notes(self) -> list[LifeNote]:
        async with self._lock:
            return [LifeNote.from_dict(note.to_dict()) for note in self._life_notes]

    async def append_life_note(self, note: LifeNote) -> None:
        async with self._lock:
            notes = list(self._life_notes)
            cleaned = _clean_note(note)
            if cleaned is None:
                return
            notes.append(cleaned)
            self._life_notes = notes

    async def consume_life_note(self) -> LifeNote | None:
        async with self._lock:
            notes = list(self._life_notes)
            if not notes:
                return None
            note = notes.pop(0)
            self._life_notes = notes
            return LifeNote.from_dict(note.to_dict())

    async def prune_life_notes(self, *, max_age_seconds: float) -> int:
        async with self._lock:
            notes = list(self._life_notes)
            kept = [
                note for note in notes
                if _note_age_seconds(note) <= max(0.0, float(max_age_seconds))
            ]
            self._life_notes = kept
            return len(notes) - len(kept)

    async def get_todos(self) -> list[Todo]:
        async with self._lock:
            return [Todo.from_dict(t.to_dict()) for t in self._todos]

    async def add_todo(self, todo: Todo) -> None:
        async with self._lock:
            self._todos.append(todo)

    async def update_todo(self, todo_id: str, **updates: Any) -> None:
        async with self._lock:
            for t in self._todos:
                if t.id == todo_id:
                    for k, v in updates.items():
                        if hasattr(t, k):
                            setattr(t, k, v)
                    t.updated_at = __import__("time").time()
                    return

    async def delete_todo(self, todo_id: str) -> None:
        async with self._lock:
            self._todos = [t for t in self._todos if t.id != todo_id]


def _clean_profile(profile: str) -> str:
    return str(profile or "").strip()


def _clean_note(note: LifeNote | str) -> LifeNote | None:
    if isinstance(note, LifeNote):
        text = " ".join(str(note.content or "").strip().split())
        if not text:
            return None
        timestamp = str(note.timestamp or "").strip() or datetime.now(UTC).isoformat()
        kind = str(note.kind or "").strip() or None
        return LifeNote(content=text, timestamp=timestamp, kind=kind)
    text = " ".join(str(note or "").strip().split())
    if not text:
        return None
    return LifeNote(content=text)


def _clean_notes(notes: list[LifeNote | str]) -> list[LifeNote]:
    cleaned: list[LifeNote] = []
    for note in notes or []:
        normalized = _clean_note(note)
        if normalized is not None:
            cleaned.append(normalized)
    return cleaned


def _note_age_seconds(note: LifeNote) -> float:
    try:
        created_at = datetime.fromisoformat(str(note.timestamp))
    except Exception:
        return 0.0
    now = datetime.now(UTC)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return max(0.0, (now - created_at.astimezone(UTC)).total_seconds())


def _agent_context(messages: list[BaseMessage], n: int) -> list[BaseMessage]:
    limit = max(0, int(n))
    if limit == 0:
        return []

    summary, raw_messages = _split_summary(messages)
    if summary is None:
        return raw_messages[-limit:]
    if limit == 1:
        return [summary]
    return [summary, *raw_messages[-(limit - 1):]]


def _raw_window(messages: list[BaseMessage], n: int) -> list[BaseMessage]:
    limit = max(0, int(n))
    if limit == 0:
        return []
    _, raw_messages = _split_summary(messages)
    return raw_messages[-limit:]


def _split_summary(messages: list[BaseMessage]) -> tuple[BaseMessage | None, list[BaseMessage]]:
    if messages and _is_compacted_summary(messages[0]):
        return messages[0], messages[1:]
    return None, list(messages)


def _is_compacted_summary(message: BaseMessage) -> bool:
    return bool(getattr(message, "additional_kwargs", {}).get("kayori_compacted"))
