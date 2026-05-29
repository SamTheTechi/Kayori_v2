from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from config.logging import get_logger
from shared_types.types import AgentGraphState

FALLBACK_TEXT = "I hit a temporary issue contacting the model. Please try again."
logger = get_logger("agent.chat.call_model")


def build_call_model_node(model: BaseChatModel, timeout_seconds: int = 60):
    async def call_model_node(state: AgentGraphState) -> dict[str, Any]:
        model_calls = int(state.get("model_calls") or 0) + 1
        messages = list(state.get("messages") or [])
        if not messages:
            return {
                "messages": [AIMessage(content=FALLBACK_TEXT)],
                "error_reason": "empty_messages",
                "model_calls": model_calls,
            }

        try:
            if hasattr(model, "ainvoke"):
                result = await asyncio.wait_for(
                    model.ainvoke(messages), timeout=timeout_seconds
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(model.invoke, messages),
                    timeout=timeout_seconds,
                )
        except Exception as exc:
            await logger.error(
                "model_call_failed",
                "Model call failed.",
                context={"timeout_seconds": timeout_seconds},
                error=exc,
            )
            return {
                "messages": [AIMessage(content=FALLBACK_TEXT)],
                "error_reason": str(exc),
                "model_calls": model_calls,
            }

        if not isinstance(result, AIMessage):
            result = AIMessage(content=getattr(result, "content", ""))
        return {"messages": [result], "model_calls": model_calls}

    return call_model_node
