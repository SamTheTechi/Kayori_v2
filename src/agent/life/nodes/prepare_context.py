from __future__ import annotations

from typing import Any

from src.shared_types.types import LifeGraphState
from src.templates.life_template import life_template


def build_prepare_context_node():
    async def prepare_context_node(state: LifeGraphState) -> dict[str, Any]:
        content = str(state.get("content") or "").strip()
        summary = str(state.get("summary") or "").strip() or "None."
        life_profile = str(state.get("life_profile") or "").strip() or "None."
        episodic = _format_episodic(list(state.get("episodic") or []))

        try:
            formatted_messages = life_template.format_messages(
                content=content or "None.",
                summary=summary,
                life_profile=life_profile,
                episodic=episodic,
            )
            return {"messages": formatted_messages, "error_reason": None}
        except Exception as exc:
            return {"messages": [], "error_reason": f"template_error:{exc}"}

    return prepare_context_node


def _format_episodic(records: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for record in records[:3]:
        fact = str(record.get("fact") or "").strip()
        context = str(record.get("context") or "").strip()
        if not fact:
            continue
        lines.append(f"- {fact}")
        if context:
            lines.append(f"  context: {context}")
    return "\n".join(lines) if lines else "None."
