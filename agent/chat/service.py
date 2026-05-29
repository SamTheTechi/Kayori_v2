from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool

from agent.chat.graph import DEFAULT_MAX_TOOL_ROUNDS, create_react_agent_graph
from config.logging import get_logger
from shared_types.models import MessageEnvelope, MoodState, MessageSource

logger = get_logger("agent.chat.service")


class ReactAgentService:
    def __init__(
        self,
        *,
        model: BaseChatModel,
        tools: list[BaseTool] | None = None,
        timeout_seconds: int = 60,
        max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
    ) -> None:
        self.model = model
        self.tools = list(tools or [])
        self.timeout_seconds = timeout_seconds
        self.max_tool_rounds = max_tool_rounds
        # Each tool round costs two graph steps (tools + call_model); plus
        # prepare_context, the initial call_model, and postprocess. Size the
        # recursion limit above that so OUR budget is the binding constraint
        # and exhaustion is handled gracefully instead of raising.
        self._recursion_limit = 2 * max(max_tool_rounds, 0) + 6
        self._graph: Any = self._build_graph()

    def _build_graph(self) -> Any:
        return create_react_agent_graph(
            model=self.model,
            tools=list(self.tools),
            timeout_seconds=self.timeout_seconds,
            max_tool_rounds=self.max_tool_rounds,
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
        if not text and envelope.source != MessageSource.PROACTIVE:
            return ""

        state_input = {
            "content": text,
            "messages": messages,
            "mood": mood,
            "episodic": list(episodic or []),
            "envelope": envelope,
        }

        try:
            result = await self._graph.ainvoke(
                state_input,
                config={"recursion_limit": self._recursion_limit},
            )
        except Exception as exc:
            await logger.error(
                "agent_failed",
                "Agent graph failed.",
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
