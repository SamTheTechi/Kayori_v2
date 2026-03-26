from __future__ import annotations

import json
from redis.asyncio import Redis

from langchain_core.messages import BaseMessage
from src.shared_types.models import EMOTIONS, MOOD_NEUTRAL, MoodState, MessagesHistory

MOOD_KEY_PREFIX = "kayori:state:mood"
HISTORY_KEY_PREFIX = "kayori:state:history"
LIFE_PROFILE_KEY_PREFIX = "kayori:state:life_profile"
LIFE_NOTES_KEY_PREFIX = "kayori:state:life_notes"

# LIVE_LOCATION_KEY = "kayori:state:live_location"
# PINNED_LOCATION_KEY = "kayori:state:pinned_location"


class RedisStateStore:
    def __init__(self, redis_client: Redis) -> None:
        self._client = redis_client

    # ------------------------------------------------------------------
    # Mood
    # ------------------------------------------------------------------

    async def get_mood(self, thread_id: str) -> MoodState:
        key = _mood_key(thread_id)
        data = await self._client.hgetall(key)
        if not data:
            await self._client.hset(
                key, mapping=dict.fromkeys(EMOTIONS, MOOD_NEUTRAL)
            )
            return MoodState()
        return MoodState.from_dict(data)

    async def set_mood(self, thread_id: str, mood: MoodState) -> None:
        payload = dict(mood.clamp().as_dict())
        await self._client.hset(_mood_key(thread_id), mapping=payload)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    async def get_history(self, thread_id: str) -> MessagesHistory:
        raw = await self._client.get(_history_key(thread_id))
        if not raw:
            return MessagesHistory()
        return MessagesHistory.from_dict(json.loads(raw))

    async def append_messages(self, thread_id: str, msgs: list[BaseMessage]) -> None:
        history = await self.get_history(thread_id)
        history.append(msgs)
        await self._client.set(_history_key(thread_id), json.dumps(history.as_dict()))

    async def replace_messages(self, thread_id: str, msgs: list[BaseMessage]) -> None:
        history = await self.get_history(thread_id)
        history.replace(msgs)
        await self._client.set(_history_key(thread_id), json.dumps(history.as_dict()))

    async def get_agent_context(self, thread_id: str, n: int) -> list[BaseMessage]:
        history = await self.get_history(thread_id)
        return _agent_context(history.all(), n)

    async def get_mood_context(self, thread_id: str, n: int) -> list[BaseMessage]:
        history = await self.get_history(thread_id)
        return _raw_window(history.all(), n)

    async def history_len(self, thread_id: str) -> int:
        history = await self.get_history(thread_id)
        return len(history)

    # ------------------------------------------------------------------
    # LIFE
    # ------------------------------------------------------------------

    async def get_life_profile(self, thread_id: str) -> str:
        raw = await self._client.get(_life_profile_key(thread_id))
        return _decode(raw).strip()

    async def replace_life_profile(self, thread_id: str, profile: str) -> None:
        await self._client.set(_life_profile_key(thread_id), _clean_profile(profile))

    async def get_life_notes(self, thread_id: str) -> list[str]:
        raw = await self._client.get(_life_notes_key(thread_id))
        if not raw:
            return []
        try:
            payload = json.loads(_decode(raw))
        except Exception:
            return []
        if not isinstance(payload, list):
            return []
        return _clean_notes([str(item) for item in payload])

    async def replace_life_notes(self, thread_id: str, notes: list[str]) -> None:
        await self._client.set(
            _life_notes_key(thread_id),
            json.dumps(_clean_notes(notes), separators=(",", ":")),
        )

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

    async def init_defaults(self, thread_id: str = "global") -> None:
        mood_key = _mood_key(thread_id)
        history_key = _history_key(thread_id)
        if not await self._client.exists(mood_key):
            await self._client.hset(
                mood_key, mapping=dict.fromkeys(EMOTIONS, MOOD_NEUTRAL)
            )
        if not await self._client.exists(history_key):
            await self._client.set(
                history_key, json.dumps(MessagesHistory().as_dict())
            )
        # if not await self._client.exists(LIVE_LOCATION_KEY):
        #     await self._client.hset(
        #         LIVE_LOCATION_KEY, mapping=LocationState().as_dict()
        #     )
        # if not await self._client.exists(PINNED_LOCATION_KEY):
        #     await self._client.hset(
        #         PINNED_LOCATION_KEY, mapping=LocationState().as_dict()
        #     )


def _thread_key(thread_id: str) -> str:
    key = str(thread_id or "").strip()
    return key or "global"


def _mood_key(thread_id: str) -> str:
    return f"{MOOD_KEY_PREFIX}:{_thread_key(thread_id)}"


def _history_key(thread_id: str) -> str:
    return f"{HISTORY_KEY_PREFIX}:{_thread_key(thread_id)}"


def _life_profile_key(thread_id: str) -> str:
    return f"{LIFE_PROFILE_KEY_PREFIX}:{_thread_key(thread_id)}"


def _life_notes_key(thread_id: str) -> str:
    return f"{LIFE_NOTES_KEY_PREFIX}:{_thread_key(thread_id)}"


def _clean_profile(profile: str) -> str:
    return str(profile or "").strip()


def _clean_notes(notes: list[str]) -> list[str]:
    cleaned: list[str] = []
    for note in notes or []:
        text = " ".join(str(note or "").strip().split())
        if text:
            cleaned.append(text)
    return cleaned


def _decode(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value or "")


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


__all__ = ["RedisStateStore"]
