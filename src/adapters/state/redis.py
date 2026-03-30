from __future__ import annotations

import json
from datetime import UTC, datetime
from redis.asyncio import Redis

from langchain_core.messages import BaseMessage
from src.shared_types.models import EMOTIONS, LifeNote, MOOD_NEUTRAL, MoodState, MessagesHistory

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

    async def list_threads(self) -> list[str]:
        prefix = f"{HISTORY_KEY_PREFIX}:"
        keys = await self._client.keys(f"{prefix}*")
        return sorted(
            _decode(key).removeprefix(prefix)
            for key in keys
            if _decode(key).startswith(prefix)
        )

    # ------------------------------------------------------------------
    # LIFE
    # ------------------------------------------------------------------

    async def get_life_profile(self, thread_id: str) -> str:
        raw = await self._client.get(_life_profile_key(thread_id))
        return _decode(raw).strip()

    async def replace_life_profile(self, thread_id: str, profile: str) -> None:
        await self._client.set(_life_profile_key(thread_id), _clean_profile(profile))

    async def get_life_notes(self, thread_id: str) -> list[LifeNote]:
        raw = await self._client.get(_life_notes_key(thread_id))
        if not raw:
            return []
        try:
            payload = json.loads(_decode(raw))
        except Exception:
            return []
        if not isinstance(payload, list):
            return []
        return _load_notes(payload)

    async def append_life_note(self, thread_id: str, note: LifeNote) -> None:
        notes = await self.get_life_notes(thread_id)
        cleaned = _clean_note(note)
        if cleaned is None:
            return
        notes.append(cleaned)
        await self._store_life_notes(thread_id, notes)

    async def consume_life_note(self, thread_id: str) -> LifeNote | None:
        notes = await self.get_life_notes(thread_id)
        if not notes:
            return None
        note = notes.pop(0)
        await self._store_life_notes(thread_id, notes)
        return note

    async def prune_life_notes(self, thread_id: str, *, max_age_seconds: float) -> int:
        notes = await self.get_life_notes(thread_id)
        kept = [
            note for note in notes
            if _note_age_seconds(note) <= max(0.0, float(max_age_seconds))
        ]
        await self._store_life_notes(thread_id, kept)
        return len(notes) - len(kept)

    async def _store_life_notes(self, thread_id: str, notes: list[LifeNote]) -> None:
        await self._client.set(
            _life_notes_key(thread_id),
            json.dumps([note.to_dict() for note in _clean_notes(notes)], separators=(",", ":")),
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


def _load_notes(payload: list[object]) -> list[LifeNote]:
    notes: list[LifeNote] = []
    for item in payload:
        if isinstance(item, dict):
            normalized = _clean_note(LifeNote.from_dict(item))
        else:
            normalized = _clean_note(str(item))
        if normalized is not None:
            notes.append(normalized)
    return notes


def _note_age_seconds(note: LifeNote) -> float:
    try:
        created_at = datetime.fromisoformat(str(note.timestamp))
    except Exception:
        return 0.0
    now = datetime.now(UTC)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return max(0.0, (now - created_at.astimezone(UTC)).total_seconds())


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
