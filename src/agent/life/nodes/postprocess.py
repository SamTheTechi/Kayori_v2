from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage

from src.shared_types.types import LifeGraphState


def build_postprocess_node():
    async def postprocess_node(state: LifeGraphState) -> dict[str, Any]:
        messages: list[BaseMessage] = list(state.get("messages") or [])
        existing_notes = _clean_notes(list(state.get("life_notes") or []))
        raw_text = ""

        for message in reversed(messages):
            if isinstance(message, AIMessage):
                raw_text = _message_text(message.content).strip()
                if raw_text:
                    break

        if not raw_text:
            return {"notes": existing_notes}

        try:
            payload = json.loads(raw_text)
        except Exception:
            return {"notes": existing_notes}

        if not isinstance(payload, dict):
            return {"notes": existing_notes}

        notes = _clean_notes(payload.get("notes") or [])
        return {"notes": notes[:3] if notes else existing_notes}

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


def _clean_notes(raw_notes: Any) -> list[str]:
    if not isinstance(raw_notes, list):
        return []
    notes: list[str] = []
    for note in raw_notes:
        text = " ".join(str(note or "").strip().split())
        if text:
            notes.append(text)
    return notes[:3]

