from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, PrivateAttr

from shared_types.models import MessageEnvelope
from shared_types.protocal import MessageBus

from tools.schemas import ReminderToolArgs


class ReminderTool(BaseTool):
    name: str = "reminder_tool"
    description: str = "Schedules a delayed reminder that re-enters the normal bus/output pipeline."
    args_schema: type[BaseModel] = ReminderToolArgs

    _bus: MessageBus = PrivateAttr()
    _fallback_user_id: str | None = PrivateAttr(default=None)

    def __init__(
        self,
        *,
        bus: MessageBus,
        fallback_user_id: str | None = None,
    ) -> None:
        super().__init__()
        self._bus = bus
        self._fallback_user_id = fallback_user_id

    async def _arun(
        self,
        delay_minutes: int = 15,
        content: str | None = None,
        target_user_id: str | None = None,
        state: dict[str, Any] | None = None,
    ) -> str:
        delay = max(1, min(24 * 60, int(delay_minutes)))
        envelope = _envelope_from_state(state)

        resolved_target = str(
            target_user_id
            or envelope.target_user_id
            or envelope.author_id
            or self._fallback_user_id
            or ""
        ).strip()
        if not resolved_target:
            return "Reminder could not be scheduled because target user id is missing."

        text = str(content or envelope.content or "").strip()
        reminder_text = f"Reminder: {text}"

        async def publish_later() -> None:
            await asyncio.sleep(delay * 60)
            await self._bus.publish(
                MessageEnvelope(
                    source="scheduler",
                    content=reminder_text,
                    is_dm=True,
                    target_user_id=resolved_target,
                    metadata={"kind": "reminder", "delay_minutes": delay},
                )
            )

        asyncio.create_task(publish_later())
        return f"Reminder scheduled in {delay} minute(s)."

    def _run(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError("Use async execution for reminder_tool.")


def _envelope_from_state(state: dict[str, Any] | None) -> MessageEnvelope:
    payload = dict(state or {})
    envelope_raw = payload.get("envelope")
    if isinstance(envelope_raw, MessageEnvelope):
        return envelope_raw
    if isinstance(envelope_raw, dict):
        return MessageEnvelope.from_dict(envelope_raw)
    return MessageEnvelope(source="tool", content="")
