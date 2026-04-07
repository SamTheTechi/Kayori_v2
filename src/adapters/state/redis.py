from __future__ import annotations

import json
from datetime import UTC, datetime
from redis.exceptions import ResponseError
from redis.asyncio import Redis

from langchain_core.messages import BaseMessage
from src.shared_types.models import InteractionState, LifeNote, MessagesHistory, MoodState

MOOD_KEY_PREFIX = "kayori:state:mood"
HISTORY_KEY_PREFIX = "kayori:state:history"
INTERACTION_KEY_PREFIX = "kayori:state:interaction"
LIFE_PROFILE_KEY_PREFIX = "kayori:state:life_profile"
LIFE_NOTES_KEY_PREFIX = "kayori:state:life_notes"


class RedisStateStore:
    def __init__(self, redis_client: Redis) -> None:
        self._client = redis_client

    async def get_mood(self) -> MoodState:
        key = _key(MOOD_KEY_PREFIX)
        raw = await self._safe_get(key)
        if raw:
            return MoodState.from_dict(_json_dict(raw))

        mood = await self._load_legacy_mood(key)
        if mood is not None:
            await self._client.set(key, _json(mood.as_dict()))
            return mood

        mood = MoodState()
        await self._client.set(key, _json(mood.as_dict()))
        return mood

    async def set_mood(self, mood: MoodState) -> None:
        await self._client.set(_key(MOOD_KEY_PREFIX), _json(mood.clamp().as_dict()))

    async def get_history(self) -> MessagesHistory:
        raw = await self._client.get(_key(HISTORY_KEY_PREFIX))
        if not raw:
            return MessagesHistory()
        return MessagesHistory.from_dict(_json_dict(raw))

    async def append_messages(self, msgs: list[BaseMessage]) -> None:
        history = await self.get_history()
        history.append(msgs)
        await self._client.set(_key(HISTORY_KEY_PREFIX), _json(history.as_dict()))

    async def replace_messages(self, msgs: list[BaseMessage]) -> None:
        history = await self.get_history()
        history.replace(msgs)
        await self._client.set(_key(HISTORY_KEY_PREFIX), _json(history.as_dict()))

    async def get_agent_context(self, n: int) -> list[BaseMessage]:
        history = await self.get_history()
        return _agent_context(history.all(), n)

    async def get_mood_context(self, n: int) -> list[BaseMessage]:
        history = await self.get_history()
        return _raw_window(history.all(), n)

    async def history_len(self) -> int:
        history = await self.get_history()
        return len(history)

    async def get_interaction_state(self) -> InteractionState:
        raw = await self._client.get(_key(INTERACTION_KEY_PREFIX))
        if not raw:
            state = InteractionState()
            await self._client.set(_key(INTERACTION_KEY_PREFIX), _json(state.as_dict()))
            return state
        return InteractionState.from_dict(_json_dict(raw))

    async def set_interaction_state(self, state: InteractionState) -> None:
        await self._client.set(
            _key(INTERACTION_KEY_PREFIX),
            _json(state.as_dict()),
        )

    async def get_life_profile(self) -> str:
        raw = await self._client.get(_key(LIFE_PROFILE_KEY_PREFIX))
        if not raw:
            return ""
        try:
            return str(_json_value(raw)).strip()
        except Exception:
            return _decode(raw).strip()

    async def replace_life_profile(self, profile: str) -> None:
        await self._client.set(
            _key(LIFE_PROFILE_KEY_PREFIX),
            _json(str(profile or "").strip()),
        )

    async def get_life_notes(self) -> list[LifeNote]:
        raw = await self._client.get(_key(LIFE_NOTES_KEY_PREFIX))
        if not raw:
            return []
        try:
            payload = _json_value(raw)
        except Exception:
            return []
        if not isinstance(payload, list):
            return []

        notes: list[LifeNote] = []
        for item in payload:
            note = LifeNote.from_dict(item) if isinstance(
                item, dict) else LifeNote(content=str(item))
            content = " ".join(str(note.content or "").strip().split())
            if not content:
                continue
            notes.append(
                LifeNote(
                    content=content,
                    timestamp=str(note.timestamp or "").strip(
                    ) or datetime.now(UTC).isoformat(),
                    kind=str(note.kind or "").strip() or None,
                )
            )
        return notes

    async def append_life_note(self, note: LifeNote) -> None:
        notes = await self.get_life_notes()
        content = " ".join(str(note.content or "").strip().split())
        if not content:
            return
        notes.append(
            LifeNote(
                content=content,
                timestamp=str(note.timestamp or "").strip(
                ) or datetime.now(UTC).isoformat(),
                kind=str(note.kind or "").strip() or None,
            )
        )
        await self._store_life_notes(notes)

    async def consume_life_note(self) -> LifeNote | None:
        notes = await self.get_life_notes()
        if not notes:
            return None
        note = notes.pop(0)
        await self._store_life_notes(notes)
        return note

    async def prune_life_notes(self, *, max_age_seconds: float) -> int:
        notes = await self.get_life_notes()
        limit = max(0.0, float(max_age_seconds))
        kept = []
        now = datetime.now(UTC)
        for note in notes:
            try:
                created_at = datetime.fromisoformat(str(note.timestamp))
            except Exception:
                created_at = now
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            if (now - created_at.astimezone(UTC)).total_seconds() <= limit:
                kept.append(note)
        await self._store_life_notes(kept)
        return len(notes) - len(kept)

    async def _store_life_notes(self, notes: list[LifeNote]) -> None:
        await self._client.set(
            _key(LIFE_NOTES_KEY_PREFIX),
            _json([
                {
                    "content": " ".join(str(note.content or "").strip().split()),
                    "timestamp": str(note.timestamp or "").strip() or datetime.now(UTC).isoformat(),
                    "kind": str(note.kind or "").strip() or None,
                }
                for note in notes
                if " ".join(str(note.content or "").strip().split())
            ]),
        )

    async def _safe_get(self, key: str) -> object | None:
        try:
            return await self._client.get(key)
        except ResponseError:
            return None

    async def _load_legacy_mood(self, key: str) -> MoodState | None:
        legacy = await self._client.hgetall(key)
        if not legacy:
            return None
        return MoodState.from_dict(
            {_decode(name): _decode(value) for name, value in legacy.items()}
        )

    async def init_defaults(self) -> None:
        mood_key = _key(MOOD_KEY_PREFIX)
        history_key = _key(HISTORY_KEY_PREFIX)
        if not await self._client.exists(mood_key):
            await self._client.set(mood_key, _json(MoodState().as_dict()))
        if not await self._client.exists(history_key):
            await self._client.set(history_key, _json(MessagesHistory().as_dict()))


def _decode(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value or "")


def _json_value(raw: object) -> object:
    return json.loads(_decode(raw))


def _json_dict(raw: object) -> dict[str, object]:
    payload = _json_value(raw)
    if isinstance(payload, dict):
        return payload
    return {}


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"))


def _key(prefix: str) -> str:
    return prefix


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
