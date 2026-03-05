from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.messages import AIMessage

from shared_types.types import AgentGraphState


FALLBACK_TEXT = "I hit a temporary issue contacting the model. Please try again."


def build_call_model_node(model: Any, timeout_seconds: int = 60):
    async def call_model_node(state: AgentGraphState) -> dict[str, Any]:
        messages = list(state.get("messages") or [])
        if not messages:
            return {"messages": [AIMessage(content=FALLBACK_TEXT)], "error_reason": "empty_messages"}

        try:
            if hasattr(model, "ainvoke"):
                result = await asyncio.wait_for(model.ainvoke(messages), timeout=timeout_seconds)
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(model.invoke, messages),
                    timeout=timeout_seconds,
                )
        except Exception as exc:
            print(exc, "error message")
            return {
                "messages": [AIMessage(content=FALLBACK_TEXT)],
                "error_reason": str(exc),
            }

        if not isinstance(result, AIMessage):
            result = AIMessage(content=getattr(result, "content", ""))
        return {"messages": [result]}

    return call_model_node
