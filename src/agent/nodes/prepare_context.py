from __future__ import annotations

from datetime import datetime
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage

from shared_types.models import MOOD_NEUTRAL, MoodState
from shared_types.types import AgentGraphState
from templates.chat_template import private_template


def build_prepare_context_node():
    async def prepare_context_node(state: AgentGraphState) -> dict[str, Any]:
        text = str(state.get("user_text") or "").strip()
        if not text:
            return {"reply_text": "", "messages": []}

        history = list(state.get("history") or [])
        messages: list[BaseMessage] = [*history, HumanMessage(content=text)]
        mood_values = _mood_values(state.get("mood"))
        current_time = datetime.now().astimezone().isoformat(timespec="seconds")

        try:
            formatted_messages = private_template.format_messages(
                messages=messages,
                current_time=current_time,
                **mood_values,
            )
            return {"messages": formatted_messages, "error_reason": None}
        except Exception as exc:
            return {"messages": messages, "error_reason": f"template_error:{exc}"}

    return prepare_context_node


def _mood_values(mood: MoodState | None) -> dict[str, float]:
    defaults = {
        "Affection": MOOD_NEUTRAL,
        "Amused": MOOD_NEUTRAL,
        "Confidence": MOOD_NEUTRAL,
        "Frustrated": MOOD_NEUTRAL,
        "Concerned": MOOD_NEUTRAL,
        "Curious": MOOD_NEUTRAL,
        "Trust": MOOD_NEUTRAL,
        "Calmness": MOOD_NEUTRAL,
    }
    if mood is None:
        return defaults

    values = mood.as_dict()
    return {
        "Affection": float(values.get("Affection", MOOD_NEUTRAL)),
        "Amused": float(values.get("Amused", MOOD_NEUTRAL)),
        "Confidence": float(values.get("Confidence", MOOD_NEUTRAL)),
        "Frustrated": float(values.get("Frustrated", MOOD_NEUTRAL)),
        "Concerned": float(values.get("Concerned", MOOD_NEUTRAL)),
        "Curious": float(values.get("Curious", MOOD_NEUTRAL)),
        "Trust": float(values.get("Trust", MOOD_NEUTRAL)),
        "Calmness": float(values.get("Calmness", MOOD_NEUTRAL)),
    }
