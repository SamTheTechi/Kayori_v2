from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage

from config.logging import get_logger
from shared_types.types import AgentGraphState

EMPTY_REPLY_TEXT = "I couldn't produce a reply just now."
BUDGET_REPLY_TEXT = (
    "I got a bit caught up looking into that and ran out of steam before "
    "wrapping it up — mind nudging me again?"
)
logger = get_logger("agent.chat.postprocess")


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts).strip()
    return str(content)


def build_postprocess_node():
    async def postprocess_node(state: AgentGraphState) -> dict[str, Any]:
        messages: list[BaseMessage] = list(state.get("messages") or [])
        reply_text = ""

        for message in reversed(messages):
            if isinstance(message, AIMessage):
                if getattr(message, "tool_calls", None):
                    continue
                reply_text = _message_text(message.content).strip()
                break

        # We only reach postprocess with a tool-calling AIMessage last when the
        # tool-round budget cut the loop short. Salvage any text the model
        # already produced; otherwise fall back to a graceful wrap-up line.
        last_ai = next(
            (m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        budget_cut = bool(last_ai is not None and getattr(
            last_ai, "tool_calls", None))

        if not reply_text and budget_cut:
            reply_text = _message_text(last_ai.content).strip() or BUDGET_REPLY_TEXT
            await logger.warning(
                "tool_budget_exhausted",
                "Tool-round budget exhausted; stopped tool loop and replied.",
                context={"model_calls": int(state.get("model_calls") or 0)},
            )

        if not reply_text:
            reply_text = EMPTY_REPLY_TEXT

        return {"reply_text": reply_text}

    return postprocess_node
