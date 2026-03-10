from __future__ import annotations

import redis.asyncio as redis

from shared_types.models import EMOTIONS, MOOD_NEUTRAL, LocationState, MoodState

MOOD_KEY = "kayori:state:mood"
LIVE_LOCATION_KEY = "kayori:state:live_location"
PINNED_LOCATION_KEY = "kayori:state:pinned_location"


class RedisStateStore:
    def __init__(self, redis_url: str) -> None:
        self._client = redis.from_url(redis_url, decode_responses=True)

    async def get_mood(self) -> MoodState:
        data = await self._client.hgetall(MOOD_KEY)
        if not data:
            return MoodState()
        return MoodState.from_dict(data)

    async def set_mood(self, mood: MoodState) -> None:
        payload = dict(mood.clamp().as_dict())
        await self._client.hset(MOOD_KEY, mapping=payload)

    async def get_live_location(self) -> LocationState:
        data = await self._client.hgetall(LIVE_LOCATION_KEY)
        if not data:
            return LocationState()
        return LocationState.from_dict(data)

    async def set_live_location(self, location: LocationState) -> None:
        await self._client.hset(LIVE_LOCATION_KEY, mapping=location.as_dict())

    async def get_pinned_location(self) -> LocationState:
        data = await self._client.hgetall(PINNED_LOCATION_KEY)
        if not data:
            return LocationState()
        return LocationState.from_dict(data)

    async def set_pinned_location(self, location: LocationState) -> None:
        await self._client.hset(PINNED_LOCATION_KEY, mapping=location.as_dict())

    async def init_defaults(self) -> None:
        if not await self._client.exists(MOOD_KEY):
            await self._client.hset(
                MOOD_KEY, mapping=dict.fromkeys(EMOTIONS, MOOD_NEUTRAL)
            )
        if not await self._client.exists(LIVE_LOCATION_KEY):
            await self._client.hset(
                LIVE_LOCATION_KEY, mapping=LocationState().as_dict()
            )
        if not await self._client.exists(PINNED_LOCATION_KEY):
            await self._client.hset(
                PINNED_LOCATION_KEY, mapping=LocationState().as_dict()
            )
