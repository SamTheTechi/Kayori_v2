from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from langchain_groq import ChatGroq

from agent.react_agent import create_react_agent_graph
from logger import get_logger
from shared_types.models import MoodState

logger = get_logger("agent.service")


@dataclass(slots=True)
class ReactAgentService:
    model: Any
    tools: list[BaseTool] = field(default_factory=list)
    max_history_messages: int = 16
    timeout_seconds: int = 60

    _graph: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.max_history_messages = max(2, self.max_history_messages)
        self._graph = create_react_agent_graph(
            model=self.model,
            tools=list(self.tools),
            max_history_messages=self.max_history_messages,
            timeout_seconds=self.timeout_seconds,
        )

    @classmethod
    def from_env(
        cls,
        *,
        model_name: str = "llama-3.3-70b-versatile",
        temperature: float = 0.7,
        tools: list[BaseTool] | None = None,
        max_history_messages: int = 16,
        timeout_seconds: int = 60,
    ) -> ReactAgentService:
        from os import getenv

        model = ChatGroq(
            model=model_name,
            temperature=temperature,
            api_key=getenv("API_KEY"),
        )
        return cls(
            model=model,
            tools=list(tools or []),
            max_history_messages=max_history_messages,
            timeout_seconds=timeout_seconds,
        )

    async def respond(
        self,
        *,
        message: str,
        thread_id: str,
        mood: MoodState | None = None,
    ) -> str:
        text = (message or "").strip()
        if not text:
            return ""

        state_input = {
            "message": text,
            "thread_id": thread_id,
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
