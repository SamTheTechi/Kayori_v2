from __future__ import annotations

import asyncio
from langchain_core.messages import BaseMessage
from shared_types.models import MoodState, MessagesHistory


class InMemoryStateStore:
    def __init__(self) -> None:
        self._mood = MoodState()
        self._history = MessagesHistory()
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

    async def get_window(self, n: int) -> list[BaseMessage]:
        async with self._lock:
            return self._history.get_window(n)

    async def history_len(self) -> int:
        async with self._lock:
            return len(self._history)

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
