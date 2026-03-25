from __future__ import annotations

from datetime import datetime
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage

from src.shared_types.models import EMOTIONS, MOOD_NEUTRAL, MoodState
from src.shared_types.types import AgentGraphState
from src.templates.chat_template import private_template


def build_prepare_context_node():
    async def prepare_context_node(state: AgentGraphState) -> dict[str, Any]:
        content = str(state.get("content") or "").strip()
        if not content:
            return {"reply_text": "", "messages": []}

        history = list(state.get("messages") or [])
        episodic = _format_episodic(list(state.get("episodic") or []))
        messages: list[BaseMessage] = [*history, HumanMessage(content=content)]
        mood_values = _all_mood_values(state.get("mood"))
        current_time = datetime.now().astimezone().isoformat(timespec="seconds")

        try:
            formatted_messages = private_template.format_messages(
                messages=messages,
                episodic=episodic,
                current_time=current_time,
                **mood_values,
            )
            return {"messages": formatted_messages, "error_reason": None}
        except Exception as exc:
            return {"messages": messages, "error_reason": f"template_error:{exc}"}

    return prepare_context_node


def _all_mood_values(mood: MoodState | None) -> dict[str, float]:
    defaults = {emotion: MOOD_NEUTRAL for emotion in EMOTIONS}
    if mood is None:
        return defaults

    values = mood.as_dict()
    return {
        emotion: float(values.get(emotion, MOOD_NEUTRAL))
        for emotion in EMOTIONS
    }


def _format_episodic(records: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for record in records[:5]:
        fact = str(record.get("fact") or "").strip()
        context = str(record.get("context") or "").strip()
        if not fact:
            continue

        lines.append(f"- {fact}")
        if context:
            lines.append(f"  context: {context}")

    return "\n".join(lines) if lines else "None."
