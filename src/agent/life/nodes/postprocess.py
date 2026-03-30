from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage

from src.shared_types.types import LifeGraphState


def build_postprocess_node():
    async def postprocess_node(state: LifeGraphState) -> dict[str, Any]:
        messages: list[BaseMessage] = list(state.get("messages") or [])
        raw_text = ""

        for message in reversed(messages):
            if isinstance(message, AIMessage):
                raw_text = _message_text(message.content).strip()
                if raw_text:
                    break

        if not raw_text:
            return {"note": None}

        try:
            payload = json.loads(raw_text)
        except Exception:
            return {"note": None}

        if not isinstance(payload, dict):
            return {"note": None}

        return {"note": _clean_note(payload.get("note"))}

    return postprocess_node


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
    return str(content or "")


def _clean_note(value: Any) -> str | None:
    text = " ".join(str(value or "").strip().split())
    return text or None
