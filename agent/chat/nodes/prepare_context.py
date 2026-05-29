from __future__ import annotations

from datetime import datetime
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from shared_types.models import EMOTIONS, MOOD_NEUTRAL, MessageSource, MoodState
from shared_types.types import AgentGraphState
from agent.prompts.chat_template import private_template


def build_prepare_context_node():
    async def prepare_context_node(state: AgentGraphState) -> dict[str, Any]:
        content = str(state.get("content") or "").strip()
        envelope = state.get("envelope")
        if not content and not (
            envelope is not None and envelope.source == MessageSource.PROACTIVE
        ):
            return {"reply_text": "", "messages": []}

        history = list(state.get("messages") or [])
        episodic = _format_episodic(list(state.get("episodic") or []))
        messages: list[BaseMessage] = list(history)
        if envelope is not None and envelope.source == MessageSource.PROACTIVE:
            time_since = str(dict(envelope.metadata or {}).get(
                "time_since_last", "a while"))
            messages.append(
                SystemMessage(
                    content=(
                        "This is a proactive outreach moment, not a user message. "
                        "Use the instruction below as an internal trigger only. "
                        f"It has been {time_since} since the user last said anything. "
                        "Let this influence how you open — warmer if it's been a while, "
                        "lighter if it's fresh. "
                        "If it helps you avoid stale or generic outreach, use "
                        "`life_info_tool` for private continuity or TavilySearch for "
                        "fresh real-world texture before you write the message."
                    )
                )
            )
            messages.append(
                SystemMessage(
                    content=(
                        "Send one short natural check-in first. Keep it simple, human, "
                        "and self-started. Vary your opening each time."
                    )
                )
            )
        else:
            messages.append(HumanMessage(content=content))
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
