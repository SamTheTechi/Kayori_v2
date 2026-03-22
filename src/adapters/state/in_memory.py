from __future__ import annotations

import asyncio
from langchain_core.messages import BaseMessage
from src.shared_types.models import MoodState, MessagesHistory


class InMemoryStateStore:
    def __init__(self) -> None:
        self._moods: dict[str, MoodState] = {}
        self._histories: dict[str, MessagesHistory] = {}
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

    async def get_window(self, thread_id: str, n: int) -> list[BaseMessage]:
        async with self._lock:
            history = self._get_or_create_history(thread_id)
            return history.get_window(n)

    async def history_len(self, thread_id: str) -> int:
        async with self._lock:
            history = self._get_or_create_history(thread_id)
            return len(history)

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
