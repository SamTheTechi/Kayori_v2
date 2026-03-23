from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, PrivateAttr

from src.core.outputsink import OutputSink
from src.shared_types.models import MessageEnvelope, MessageSource, OutboundMessage
from src.shared_types.tool_schemas import ReminderToolArgs


class ReminderTool(BaseTool):
    name: str = "reminder_tool"
    description: str = "Schedules a delayed reminder that is delivered directly to the configured outputs."
    args_schema: type[BaseModel] = ReminderToolArgs

    _output: OutputSink = PrivateAttr()
    _fallback_user_id: str | None = PrivateAttr(default=None)

    def __init__(
        self,
        *,
        output: OutputSink,
        fallback_user_id: str | None = None,
    ) -> None:
        super().__init__()
        self._output = output
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
        if envelope is None:
            return "Reminder could not be scheduled because no message context was available."

        delivery_source = _delivery_source_from_envelope(envelope)
        if delivery_source is None:
            return "Reminder could not be scheduled because no delivery source was available."

        route = _resolve_route(
            envelope=envelope,
            explicit_target_user_id=target_user_id,
            fallback_user_id=self._fallback_user_id,
        )
        if route is None:
            return "Reminder could not be scheduled because no delivery target was available."

        text = str(content or envelope.content or "").strip()
        if not text:
            return "Reminder could not be scheduled because reminder text is empty."
        reminder_text = f"Reminder: {text}"

        async def send_later() -> None:
            await asyncio.sleep(delay * 60)
            await self._output.send(
                OutboundMessage(
                    source=delivery_source,
                    content=reminder_text,
                    channel_id=route["channel_id"],
                    target_user_id=route["target_user_id"],
                    created_at=datetime.now(UTC).isoformat(),
                    metadata={
                        "kind": "reminder_delivery",
                        "origin_source": MessageSource.REMINDER.value,
                        "delay_minutes": delay,
                        "origin_message_id": envelope.message_id,
                    },
                )
            )

        asyncio.create_task(send_later())
        return f"Reminder scheduled in {delay} minute(s)."

    def _run(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError("Use async execution for reminder_tool.")


def _envelope_from_state(state: dict[str, Any] | None) -> MessageEnvelope | None:
    payload = dict(state or {})
    envelope_raw = payload.get("envelope")
    if isinstance(envelope_raw, MessageEnvelope):
        return envelope_raw
    if isinstance(envelope_raw, dict):
        return MessageEnvelope.from_dict(envelope_raw)
    return None


def _resolve_route(
    *,
    envelope: MessageEnvelope,
    explicit_target_user_id: str | None,
    fallback_user_id: str | None,
) -> dict[str, str | None] | None:
    target_user_id = (
        str(explicit_target_user_id or envelope.target_user_id or "").strip() or None
    )
    if target_user_id:
        return {"target_user_id": target_user_id, "channel_id": None}

    channel_id = str(envelope.channel_id or "").strip() or None
    if channel_id:
        return {"target_user_id": None, "channel_id": channel_id}

    target_user_id = str(
        envelope.author_id or fallback_user_id or "").strip() or None
    if target_user_id:
        return {"target_user_id": target_user_id, "channel_id": None}

    return None


def _delivery_source_from_envelope(envelope: MessageEnvelope) -> MessageSource | None:
    if envelope.source in {
        MessageSource.CONSOLE,
        MessageSource.DISCORD,
        MessageSource.TELEGRAM,
    }:
        return envelope.source
    return None
