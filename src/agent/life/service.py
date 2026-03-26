from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from src.agent.life.graph import create_life_agent_graph
from src.logger import get_logger

logger = get_logger("agent.life.service")


class LifeAgentService:
    def __init__(
        self,
        *,
        model: BaseChatModel,
        timeout_seconds: int = 60,
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._graph: Any = self._build_graph()

    def _build_graph(self) -> Any:
        return create_life_agent_graph(
            model=self.model,
            timeout_seconds=self.timeout_seconds,
        )

    async def reflect(
        self,
        *,
        content: str,
        messages: list[BaseMessage] | None = None,
        episodic: list[dict[str, Any]] | None = None,
        life_profile: str = "",
        life_notes: list[str] | None = None,
    ) -> list[str]:
        state_input = {
            "content": str(content or "").strip(),
            "messages": list(messages or []),
            "episodic": list(episodic or []),
            "life_profile": str(life_profile or "").strip(),
            "life_notes": list(life_notes or []),
        }

        try:
            result = await self._graph.ainvoke(state_input)
        except Exception as exc:
            await logger.exception(
                "life_graph_invoke_failed",
                "LIFE graph invocation failed.",
                error=exc,
            )
            return list(life_notes or [])

        notes = result.get("notes") or []
        if not isinstance(notes, list):
            return list(life_notes or [])
        return [str(note).strip() for note in notes if str(note).strip()][:3]
