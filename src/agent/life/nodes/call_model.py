from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from src.logger import get_logger
from src.shared_types.types import LifeGraphState

logger = get_logger("agent.life.call_model")


def build_call_model_node(model: BaseChatModel, timeout_seconds: int = 60):
    async def call_model_node(state: LifeGraphState) -> dict[str, Any]:
        messages = list(state.get("messages") or [])
        if not messages:
            return {
                "messages": [AIMessage(content='{"note": null}')],
                "error_reason": "empty_messages",
            }

        try:
            if hasattr(model, "ainvoke"):
                result = await asyncio.wait_for(
                    model.ainvoke(messages),
                    timeout=timeout_seconds,
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(model.invoke, messages),
                    timeout=timeout_seconds,
                )
        except Exception as exc:
            await logger.error(
                "life_model_call_failed",
                "LIFE model call failed.",
                context={"timeout_seconds": timeout_seconds},
                error=exc,
            )
            return {
                "messages": [AIMessage(content='{"note": null}')],
                "error_reason": str(exc),
            }

        if not isinstance(result, AIMessage):
            result = AIMessage(content=getattr(result, "content", ""))
        return {"messages": [result]}

    return call_model_node
