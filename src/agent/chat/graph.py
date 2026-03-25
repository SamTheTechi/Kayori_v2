from __future__ import annotations

from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool
from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from src.agent.chat.nodes.call_model import build_call_model_node
from src.agent.chat.nodes.postprocess import build_postprocess_node
from src.agent.chat.nodes.prepare_context import build_prepare_context_node
from src.shared_types.types import AgentGraphState


def create_react_agent_graph(
    *,
    model: BaseChatModel,
    tools: list[BaseTool],
    timeout_seconds: int = 60,
) -> CompiledStateGraph:
    graph = StateGraph(AgentGraphState)

    bound_model = model.bind_tools(tools) if tools else model

    graph.add_node(
        "prepare_context",
        build_prepare_context_node()
    )
    graph.add_node(
        "call_model",
        build_call_model_node(
            model=bound_model,
            timeout_seconds=timeout_seconds
        ),
    )
    graph.add_node(
        "postprocess",
        build_postprocess_node()
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

    graph.add_edge("postprocess", END)

    return graph.compile()
