from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool

from src.agent.chat.graph import create_react_agent_graph
from src.logger import get_logger
from src.shared_types.models import MessageEnvelope, MoodState

logger = get_logger("agent.chat.service")


class ReactAgentService:
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
        return create_react_agent_graph(
            model=self.model,
            tools=list(self.tools),
            timeout_seconds=self.timeout_seconds,
        )

    async def respond(
        self,
        *,
        content: str,
        messages: list[BaseMessage] | None = None,
        mood: MoodState | None = None,
        episodic: list[dict[str, Any]] | None = None,
        envelope: MessageEnvelope,
    ) -> str:
        text = (content or "").strip()
        if not text:
            return ""

        state_input = {
            "content": text,
            "messages": messages,
            "mood": mood,
            "episodic": list(episodic or []),
            "envelope": envelope,
        }

        try:
            result = await self._graph.ainvoke(state_input)
        except Exception as exc:
            await logger.exception(
                "agent_graph_invoke_failed",
                "Agent graph invocation failed.",
                context={
                    "source": str(envelope.source),
                    "channel_id": envelope.channel_id,
                    "target_user_id": envelope.target_user_id,
                },
                error=exc,
            )
            return "I hit a temporary issue contacting the model. Please try again."

        reply_text = str(result.get("reply_text") or "").strip()
        if not reply_text:
            return "I couldn't produce a reply just now."
        return reply_text
