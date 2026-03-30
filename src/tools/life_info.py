from __future__ import annotations

import os
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, PrivateAttr

from src.shared_types.models import LifeNote, MessageEnvelope
from src.shared_types.protocol import StateStore
from src.shared_types.thread_identity import resolve_thread_id
from src.shared_types.tool_schemas import LifeInfoToolArgs

LIFE_NOTE_MAX_AGE_SECONDS = 60 * 60 * 24 * 3


class LifeInfoTool(BaseTool):
    name: str = "life_info_tool"
    description: str = (
        "Reads Kayori's internal LIFE context for the current thread and "
        "consumes one queued LIFE note."
    )
    args_schema: type[BaseModel] = LifeInfoToolArgs

    _state_store: StateStore = PrivateAttr()

    def __init__(self, *, state_store: StateStore) -> None:
        super().__init__()
        self._state_store = state_store

    async def _arun(
        self,
        include_profile: bool = True,
        state: dict[str, Any] | None = None,
    ) -> str:
        envelope = _envelope_from_state(state)
        if envelope is None:
            return "LIFE info is unavailable because no message context was provided."

        thread_id = _resolve_effective_thread_id(envelope)
        await self._state_store.prune_life_notes(
            thread_id,
            max_age_seconds=LIFE_NOTE_MAX_AGE_SECONDS,
        )
        note = await self._state_store.consume_life_note(thread_id)
        profile = (
            await self._state_store.get_life_profile(thread_id)
            if include_profile
            else ""
        )

        lines: list[str] = []
        if include_profile:
            lines.append("LIFE profile:")
            lines.append(profile or "None.")

        lines.append("Current LIFE note:")
        if note is not None:
            lines.append(_note_text(note))
        else:
            lines.append("None.")

        return "\n".join(lines)

    def _run(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError("Use async execution for life_info_tool.")


def _envelope_from_state(state: dict[str, Any] | None) -> MessageEnvelope | None:
    payload = dict(state or {})
    envelope_raw = payload.get("envelope")
    if isinstance(envelope_raw, MessageEnvelope):
        return envelope_raw
    if isinstance(envelope_raw, dict):
        return MessageEnvelope.from_dict(envelope_raw)
    return None


def _resolve_effective_thread_id(envelope: MessageEnvelope) -> str:
    forced_thread_id = str(os.getenv("FORCE_THREAD_ID", "")).strip()
    explicit_thread_id = str(dict(envelope.metadata or {}).get("thread_id") or "").strip()
    return (
        forced_thread_id
        or explicit_thread_id
        or resolve_thread_id(
            target_user_id=envelope.target_user_id,
            channel_id=envelope.channel_id,
            author_id=envelope.author_id,
        )
    )


def _note_text(note: LifeNote) -> str:
    return str(note.content or "").strip() or "None."
