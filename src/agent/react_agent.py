from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from agent.nodes.call_model import build_call_model_node
from agent.nodes.finalize import build_finalize_node
from agent.nodes.postprocess import build_postprocess_node
from agent.nodes.prepare_context import build_prepare_context_node
from shared_types.types import AgentGraphState


def create_react_agent_graph(
    *,
    model: Any,
    tools: list[BaseTool],
    history_store: dict,
    max_history_messages: int,
    timeout_seconds: int = 60,
) -> CompiledStateGraph:
    graph = StateGraph(AgentGraphState)

    bound_model = model.bind_tools(tools) if tools else model

    graph.add_node("prepare_context", build_prepare_context_node())
    graph.add_node(
        "call_model",
        build_call_model_node(
            model=bound_model, timeout_seconds=timeout_seconds),
    )
    graph.add_node("postprocess", build_postprocess_node())
    graph.add_node(
        "finalize",
        build_finalize_node(
            history_store=history_store,
            max_history_messages=max_history_messages,
        ),
    )

    has_tools = len(tools) > 0
    if has_tools:
        graph.add_node("tools", ToolNode(tools=tools))

    graph.add_edge(START, "prepare_context")
    graph.add_edge("prepare_context", "call_model")

    if has_tools:

        def route_after_model(state: AgentGraphState) -> str:
            messages = list(state.get("messages") or [])
            if not messages:
                return "postprocess"
            last_message = messages[-1]
            if isinstance(last_message, AIMessage) and getattr(
                last_message, "tool_calls", None
            ):
                return "tools"
            return "postprocess"

        graph.add_conditional_edges(
            "call_model",
            route_after_model,
            {
                "tools": "tools",
                "postprocess": "postprocess",
            },
        )
        graph.add_edge("tools", "call_model")
    else:
        graph.add_edge("call_model", "postprocess")

    graph.add_edge("postprocess", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()
