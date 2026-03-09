from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import BaseTool
from langchain_groq import ChatGroq

from agent.react_agent import create_react_agent_graph
from shared_types.models import MessageEnvelope, MoodState
from shared_types.protocol import ToolAuditLogger
from shared_types.types import ToolAuditEvent


@dataclass(slots=True)
class ReactAgentService:
    model: Any
    tools: list[BaseTool] = field(default_factory=list)
    max_history_messages: int = 16
    timeout_seconds: int = 60
    audit_logger: ToolAuditLogger | None = None

    _history: dict[str, list[BaseMessage]] = field(
        default_factory=dict, init=False, repr=False)
    _graph: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.max_history_messages = max(2, self.max_history_messages)
        self._graph = create_react_agent_graph(
            model=self.model,
            tools=list(self.tools),
            history_store=self._history,
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
        audit_logger: ToolAuditLogger | None = None,
    ) -> "ReactAgentService":
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
            audit_logger=audit_logger,
        )

    # def set_tools(self, tools: list[BaseTool]) -> None:
    #     self.tools = list(tools)
    #     self._graph = create_react_agent_graph(
    #         model=self.model,
    #         tools=list(self.tools),
    #         history_store=self._history,
    #         max_history_messages=self.max_history_messages,
    #         timeout_seconds=self.timeout_seconds,
    #     )
    #
    # def add_tools(self, tools: list[BaseTool]) -> None:
    #     self.set_tools([*self.tools, *list(tools)])

    async def respond(
        self,
        *,
        user_text: str,
        thread_id: str,
        mood: MoodState | None = None,
        envelope: MessageEnvelope | None = None,
    ) -> str:
        text = (user_text or "").strip()
        if not text:
            return ""

        state_input = {
            "user_text": text,
            "thread_id": thread_id,
            "mood": mood,
            "envelope": envelope,
            "history": list(self._history.get(thread_id, [])),
        }

        try:
            result = await self._graph.ainvoke(state_input)
        except Exception as exc:
            print(f"[agent] graph invoke failed for thread={thread_id}: {exc}")
            return "I hit a temporary issue contacting the model. Please try again."

        await self._audit_tool_events(
            result=result,
            thread_id=thread_id,
            envelope=envelope,
        )

        reply_text = str(result.get("reply_text") or "").strip()
        if not reply_text:
            return "I couldn't produce a reply just now."
        return reply_text

    async def _audit_tool_events(
        self,
        *,
        result: dict[str, Any],
        thread_id: str,
        envelope: MessageEnvelope | None,
    ) -> None:
        logger = self.audit_logger
        if logger is None:
            return

        all_messages = list(result.get("messages") or [])
        if not all_messages:
            return

        messages = None
        for idx in range(len(all_messages) - 1, -1, -1):
            if isinstance(all_messages[idx], HumanMessage):
                messages = all_messages[idx + 1:]
        if not messages:
            return

        source = str(getattr(envelope, "source", "") or "unknown")
        now_iso = datetime.now(timezone.utc).isoformat()
        seen: set[str] = set()

        for message in messages:
            if not isinstance(message, AIMessage):
                continue
            for call in list(getattr(message, "tool_calls", None) or []):
                tool_name = str(call.get("name") or "unknown_tool")
                tool_input = call.get("args")
                call_id = str(call.get("id") or "").strip()
                dedupe_key = call_id or f"{tool_name}:{repr(tool_input)}"
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                event: ToolAuditEvent = {
                    "timestamp": now_iso,
                    "event_type": "tool_call",
                    "thread_id": thread_id,
                    "source": source,
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                }
                try:
                    await logger.log_tool_event(event)
                except Exception as exc:
                    print(f"[audit] failed to log tool_call event: {exc}")
