from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool

from src.agent.react_agent import create_react_agent_graph
from src.logger import get_logger
from src.shared_types.models import MoodState

logger = get_logger("agent.service")


class ReactAgentService:
    def __init__(
        self,
        *,
        model: BaseChatModel,
        tools: list[BaseTool] | None = None,
        max_history_messages: int = 16,
        timeout_seconds: int = 60,
    ) -> None:
        self.model = model
        self.tools = list(tools or [])
        self.max_history_messages = max(2, max_history_messages)
        self.timeout_seconds = timeout_seconds
        self._graph: Any = self._build_graph()

    def _build_graph(self) -> Any:
        return create_react_agent_graph(
            model=self.model,
            tools=list(self.tools),
            max_history_messages=self.max_history_messages,
            timeout_seconds=self.timeout_seconds,
        )

    async def respond(
        self,
        *,
        content: str,
        thread_id: str,
        messages: list[BaseMessage] | None = None,
        mood: MoodState | None = None,
    ) -> str:
        text = (content or "").strip()
        if not text:
            return ""

        state_input = {
            "content": text,
            "thread_id": thread_id,
            "messages": messages,
            "mood": mood,
        }

        try:
            result = await self._graph.ainvoke(state_input)
        except Exception as exc:
            await logger.exception(
                "agent_graph_invoke_failed",
                "Agent graph invocation failed.",
                context={
                    "thread_id": thread_id,
                },
                error=exc,
            )
            return "I hit a temporary issue contacting the model. Please try again."

        reply_text = str(result.get("reply_text") or "").strip()
        if not reply_text:
            return "I couldn't produce a reply just now."
        return reply_text
