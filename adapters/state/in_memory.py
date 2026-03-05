from __future__ import annotations

import asyncio
import time

from shared_types.models import LocationState, MoodState


class InMemoryStateStore:
    def __init__(self) -> None:
        now = time.time()
        self._mood = MoodState()
        self._live = LocationState(
            latitude=0.0, longitude=0.0, timestamp=now)
        self._pinned = LocationState(
            latitude=0.0, longitude=0.0, timestamp=now)
        self._lock = asyncio.Lock()

    async def get_mood(self) -> MoodState:
        async with self._lock:
            return MoodState.from_dict(self._mood.as_dict())

    async def set_mood(self, mood: MoodState) -> None:
        async with self._lock:
            self._mood = MoodState.from_dict(mood.as_dict()).clamp()

    async def get_live_location(self) -> LocationState:
        async with self._lock:
            return LocationState.from_dict(self._live.as_dict())

    async def set_live_location(self, location: LocationState) -> None:
        async with self._lock:
            self._live = LocationState.from_dict(location.as_dict())

    async def get_pinned_location(self) -> LocationState:
        async with self._lock:
            return LocationState.from_dict(self._pinned.as_dict())

    async def set_pinned_location(self, location: LocationState) -> None:
        async with self._lock:
            self._pinned = LocationState.from_dict(location.as_dict())
