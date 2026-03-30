from __future__ import annotations

import asyncio
from langchain_core.messages import BaseMessage
from datetime import UTC, datetime

from src.shared_types.models import LifeNote, MoodState, MessagesHistory


class InMemoryStateStore:
    def __init__(self) -> None:
        self._moods: dict[str, MoodState] = {}
        self._histories: dict[str, MessagesHistory] = {}
        self._life_profiles: dict[str, str] = {}
        self._life_notes: dict[str, list[LifeNote]] = {}
        self._lock = asyncio.Lock()
        # now = time.time()
        # self._live = LocationState(latitude=0.0, longitude=0.0, timestamp=now)
        # self._pinned = LocationState(
        #     latitude=0.0, longitude=0.0, timestamp=now)

    # ------------------------------------------------------------------
    # Mood
    # ------------------------------------------------------------------

    async def get_mood(self, thread_id: str) -> MoodState:
        async with self._lock:
            mood = self._get_or_create_mood(thread_id)
            return MoodState.from_dict(mood.as_dict())

    async def set_mood(self, thread_id: str, mood: MoodState) -> None:
        async with self._lock:
            key = _thread_key(thread_id)
            self._moods[key] = MoodState.from_dict(mood.as_dict()).clamp()

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    async def get_history(self, thread_id: str) -> MessagesHistory:
        async with self._lock:
            history = self._get_or_create_history(thread_id)
            return MessagesHistory.from_dict(history.as_dict())

    async def append_messages(self, thread_id: str, msgs: list[BaseMessage]) -> None:
        async with self._lock:
            history = self._get_or_create_history(thread_id)
            history.append(msgs)

    async def replace_messages(self, thread_id: str, msgs: list[BaseMessage]) -> None:
        """Called after compression to swap trimmed window back in."""
        async with self._lock:
            history = self._get_or_create_history(thread_id)
            history.replace(msgs)

    async def get_agent_context(self, thread_id: str, n: int) -> list[BaseMessage]:
        async with self._lock:
            history = self._get_or_create_history(thread_id)
            return _agent_context(history.all(), n)

    async def get_mood_context(self, thread_id: str, n: int) -> list[BaseMessage]:
        async with self._lock:
            history = self._get_or_create_history(thread_id)
            return _raw_window(history.all(), n)

    async def history_len(self, thread_id: str) -> int:
        async with self._lock:
            history = self._get_or_create_history(thread_id)
            return len(history)

    async def list_threads(self) -> list[str]:
        async with self._lock:
            return sorted(self._histories.keys())

    # ------------------------------------------------------------------
    # LIFE
    # ------------------------------------------------------------------

    async def get_life_profile(self, thread_id: str) -> str:
        async with self._lock:
            return str(self._life_profiles.get(_thread_key(thread_id), ""))

    async def replace_life_profile(self, thread_id: str, profile: str) -> None:
        async with self._lock:
            self._life_profiles[_thread_key(thread_id)] = _clean_profile(profile)

    async def get_life_notes(self, thread_id: str) -> list[LifeNote]:
        async with self._lock:
            return [LifeNote.from_dict(note.to_dict()) for note in self._life_notes.get(_thread_key(thread_id), [])]

    async def append_life_note(self, thread_id: str, note: LifeNote) -> None:
        async with self._lock:
            key = _thread_key(thread_id)
            notes = list(self._life_notes.get(key, []))
            cleaned = _clean_note(note)
            if cleaned is None:
                return
            notes.append(cleaned)
            self._life_notes[key] = notes

    async def consume_life_note(self, thread_id: str) -> LifeNote | None:
        async with self._lock:
            key = _thread_key(thread_id)
            notes = list(self._life_notes.get(key, []))
            if not notes:
                return None
            note = notes.pop(0)
            self._life_notes[key] = notes
            return LifeNote.from_dict(note.to_dict())

    async def prune_life_notes(self, thread_id: str, *, max_age_seconds: float) -> int:
        async with self._lock:
            key = _thread_key(thread_id)
            notes = list(self._life_notes.get(key, []))
            kept = [
                note for note in notes
                if _note_age_seconds(note) <= max(0.0, float(max_age_seconds))
            ]
            self._life_notes[key] = kept
            return len(notes) - len(kept)

    # ------------------------------------------------------------------
    # Location
    # ------------------------------------------------------------------

    # async def get_live_location(self) -> LocationState:
    #     async with self._lock:
    #         return LocationState.from_dict(self._live.as_dict())
    #
    # async def set_live_location(self, location: LocationState) -> None:
    #     async with self._lock:
    #         self._live = LocationState.from_dict(location.as_dict())
    #
    # async def get_pinned_location(self) -> LocationState:
    #     async with self._lock:
    #         return LocationState.from_dict(self._pinned.as_dict())
    #
    # async def set_pinned_location(self, location: LocationState) -> None:
    #     async with self._lock:
    #         self._pinned = LocationState.from_dict(location.as_dict())

    def _get_or_create_mood(self, thread_id: str) -> MoodState:
        key = _thread_key(thread_id)
        mood = self._moods.get(key)
        if mood is None:
            mood = MoodState()
            self._moods[key] = mood
        return mood

    def _get_or_create_history(self, thread_id: str) -> MessagesHistory:
        key = _thread_key(thread_id)
        history = self._histories.get(key)
        if history is None:
            history = MessagesHistory()
            self._histories[key] = history
        return history


def _thread_key(thread_id: str) -> str:
    key = str(thread_id or "").strip()
    return key or "global"


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
