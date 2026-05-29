from __future__ import annotations

from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool
from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from agent.chat.nodes.call_model import build_call_model_node
from agent.chat.nodes.postprocess import build_postprocess_node
from agent.chat.nodes.prepare_context import build_prepare_context_node
from shared_types.types import AgentGraphState

# Maximum number of tool-execution rounds allowed within a single turn before
# the agent is forced to stop calling tools and produce a reply. Guards against
# runaway tool loops (and the model spend they incur).
DEFAULT_MAX_TOOL_ROUNDS = 6


def create_react_agent_graph(
    *,
    model: BaseChatModel,
    tools: list[BaseTool],
    timeout_seconds: int = 60,
    max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
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
                # `model_calls` counts call_model executions; after the n-th call
                # the n-th tool round would run, so allow tools only while
                # model_calls <= max_tool_rounds. Beyond that, stop and reply.
                model_calls = int(state.get("model_calls") or 0)
                if model_calls > max_tool_rounds:
                    return "postprocess"
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
