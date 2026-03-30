from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel

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
        summary: str = "",
        episodic: list[dict[str, Any]] | None = None,
        life_profile: str = "",
    ) -> str | None:
        state_input = {
            "content": str(content or "").strip(),
            "summary": str(summary or "").strip(),
            "episodic": list(episodic or []),
            "life_profile": str(life_profile or "").strip(),
        }

        try:
            result = await self._graph.ainvoke(state_input)
        except Exception as exc:
            await logger.error(
                "life_failed",
                "LIFE graph failed.",
                error=exc,
            )
            return None

        note = " ".join(str(result.get("note") or "").strip().split())
        return note or None
