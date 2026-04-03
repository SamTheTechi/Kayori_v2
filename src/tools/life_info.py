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
        "Use this when the user asks about Kayori's life, inner state, what "
        "she has been carrying lately, or explicitly asks to use LIFE. "
        "Returns authored LIFE profile context and recent LIFE notes."
    )
    args_schema: type[BaseModel] = LifeInfoToolArgs

    _state_store: StateStore = PrivateAttr()

    def __init__(self, *, state_store: StateStore) -> None:
        super().__init__()
        self._state_store = state_store

    async def _arun(
        self,
        include_profile: bool = True,
        note_action: str = "peek",
        max_notes: int = 1,
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
        profile = (
            await self._state_store.get_life_profile()
            if include_profile
            else ""
        )
        notes = await _resolve_notes(
            self._state_store,
            thread_id,
            note_action=str(note_action or "peek").strip().lower(),
            max_notes=max_notes,
        )

        lines: list[str] = []
        if include_profile:
            lines.append("LIFE profile:")
            lines.append(profile or "None.")

        if note_action != "skip":
            label = (
                "Consumed LIFE note:"
                if str(note_action or "").strip().lower() == "consume"
                else "Pending LIFE notes:"
            )
            lines.append(label)
            if notes:
                lines.extend(f"- {_note_text(note)}" for note in notes)
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


async def _resolve_notes(
    state_store: StateStore,
    thread_id: str,
    *,
    note_action: str,
    max_notes: int,
) -> list[LifeNote]:
    limit = max(1, min(3, int(max_notes)))
    if note_action == "skip":
        return []
    if note_action == "consume":
        notes: list[LifeNote] = []
        for _ in range(limit):
            note = await state_store.consume_life_note(thread_id)
            if note is None:
                break
            notes.append(note)
        return notes
    notes = await state_store.get_life_notes(thread_id)
    return notes[:limit]
