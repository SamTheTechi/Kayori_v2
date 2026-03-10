from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage

from shared_types.types import AgentGraphState

EMPTY_REPLY_TEXT = "I couldn't produce a reply just now."


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

        if not reply_text:
            reply_text = EMPTY_REPLY_TEXT

        return {"reply_text": reply_text}

    return postprocess_node
