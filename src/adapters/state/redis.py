from __future__ import annotations

import json
import redis.asyncio as redis

from langchain_core.messages import BaseMessage
from shared_types.models import EMOTIONS, MOOD_NEUTRAL, MoodState, MessagesHistory

MOOD_KEY = "kayori:state:mood"
HISTORY_KEY = "kayori:state:history"

# LIVE_LOCATION_KEY = "kayori:state:live_location"
# PINNED_LOCATION_KEY = "kayori:state:pinned_location"


class RedisStateStore:
    def __init__(self, redis_url: str) -> None:
        self._client = redis.from_url(redis_url, decode_responses=True)

    # ------------------------------------------------------------------
    # Mood
    # ------------------------------------------------------------------

    async def get_mood(self) -> MoodState:
        data = await self._client.hgetall(MOOD_KEY)
        if not data:
            return MoodState()
        return MoodState.from_dict(data)

    async def set_mood(self, mood: MoodState) -> None:
        payload = dict(mood.clamp().as_dict())
        await self._client.hset(MOOD_KEY, mapping=payload)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    async def get_history(self) -> MessagesHistory:
        raw = await self._client.get(HISTORY_KEY)
        if not raw:
            return MessagesHistory()
        return MessagesHistory.from_dict(json.loads(raw))

    async def append_messages(self, msgs: list[BaseMessage]) -> None:
        history = await self.get_history()
        history.append(msgs)
        await self._client.set(HISTORY_KEY, json.dumps(history.as_dict()))

    async def replace_messages(self, msgs: list[BaseMessage]) -> None:
        history = await self.get_history()
        history.replace(msgs)
        await self._client.set(HISTORY_KEY, json.dumps(history.as_dict()))

    async def get_window(self, n: int) -> list[BaseMessage]:
        history = await self.get_history()
        return history.get_window(n)

    async def history_len(self) -> int:
        history = await self.get_history()
        return len(history)

    # ------------------------------------------------------------------
    # Location
    # ------------------------------------------------------------------

    # async def get_live_location(self) -> LocationState:
    #     data = await self._client.hgetall(LIVE_LOCATION_KEY)
    #     if not data:
    #         return LocationState()
    #     return LocationState.from_dict(data)
    #
    # async def set_live_location(self, location: LocationState) -> None:
    #     await self._client.hset(LIVE_LOCATION_KEY, mapping=location.as_dict())
    #
    # async def get_pinned_location(self) -> LocationState:
    #     data = await self._client.hgetall(PINNED_LOCATION_KEY)
    #     if not data:
    #         return LocationState()
    #     return LocationState.from_dict(data)
    #
    # async def set_pinned_location(self, location: LocationState) -> None:
    #     await self._client.hset(PINNED_LOCATION_KEY, mapping=location.as_dict())

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    async def init_defaults(self) -> None:
        if not await self._client.exists(MOOD_KEY):
            await self._client.hset(
                MOOD_KEY, mapping=dict.fromkeys(EMOTIONS, MOOD_NEUTRAL)
            )
        if not await self._client.exists(HISTORY_KEY):
            await self._client.set(
                HISTORY_KEY, json.dumps(MessagesHistory().as_dict())
            )
        # if not await self._client.exists(LIVE_LOCATION_KEY):
        #     await self._client.hset(
        #         LIVE_LOCATION_KEY, mapping=LocationState().as_dict()
        #     )
        # if not await self._client.exists(PINNED_LOCATION_KEY):
        #     await self._client.hset(
        #         PINNED_LOCATION_KEY, mapping=LocationState().as_dict()
        #     )
