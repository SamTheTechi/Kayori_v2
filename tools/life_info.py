from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, PrivateAttr

from shared_types.models import LifeNote
from shared_types.protocol import StateStore
from shared_types.tool_schemas import LifeInfoToolArgs

LIFE_NOTE_MAX_AGE_SECONDS = 60 * 60 * 24 * 3


class LifeInfoTool(BaseTool):
    name: str = "life_info_tool"
    description: str = "Store or retrieve life profile notes."
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
        del state

        await self._state_store.prune_life_notes(
            max_age_seconds=LIFE_NOTE_MAX_AGE_SECONDS,
        )
        profile = (
            await self._state_store.get_life_profile()
            if include_profile
            else ""
        )
        notes = await _resolve_notes(
            self._state_store,
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


def _note_text(note: LifeNote) -> str:
    return str(note.content or "").strip() or "None."


async def _resolve_notes(
    state_store: StateStore,
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
            note = await state_store.consume_life_note()
            if note is None:
                break
            notes.append(note)
        return notes
    notes = await state_store.get_life_notes()
    return notes[:limit]


from tools import registry  # noqa: E402

registry.register(
    "life_info_tool",
    description="Store or retrieve life profile notes.",
    toolset="utility",
    factory=lambda state_store=None, **kw: [LifeInfoTool(state_store=state_store)] if state_store else [],
)
