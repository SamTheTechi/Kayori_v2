from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from agent.life.graph import create_life_agent_graph
from config.logging import get_logger

logger = get_logger("agent.life.service")


class LifeAgentService:
    def __init__(
        self,
        *,
        model: BaseChatModel,
        tools: list[BaseTool] | None = None,
        timeout_seconds: int = 60,
    ) -> None:
        self.model = model
        self.tools = list(tools or [])
        self.timeout_seconds = timeout_seconds
        self._graph: Any = self._build_graph()

    def _build_graph(self) -> Any:
        return create_life_agent_graph(
            model=self.model,
            tools=list(self.tools),
            timeout_seconds=self.timeout_seconds,
        )

    async def reflect(
        self,
        *,
        content: str,
        summary: str = "",
        episodic: list[dict[str, Any]] | None = None,
        life_profile: str = "",
        recent_notes: list[str] | None = None,
    ) -> str | None:
        state_input = {
            "content": str(content or "").strip(),
            "summary": str(summary or "").strip(),
            "episodic": list(episodic or []),
            "life_profile": str(life_profile or "").strip(),
            "recent_notes": [
                " ".join(str(note or "").strip().split())
                for note in list(recent_notes or [])
                if " ".join(str(note or "").strip().split())
            ],
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
