from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agent.life.nodes.call_model import build_call_model_node
from src.agent.life.nodes.postprocess import build_postprocess_node
from src.agent.life.nodes.prepare_context import build_prepare_context_node
from src.shared_types.types import LifeGraphState


def create_life_agent_graph(
    *,
    model: BaseChatModel,
    timeout_seconds: int = 60,
) -> CompiledStateGraph:
    graph = StateGraph(LifeGraphState)

    graph.add_node("prepare_context", build_prepare_context_node())
    graph.add_node(
        "call_model",
        build_call_model_node(
            model=model,
            timeout_seconds=timeout_seconds,
        ),
    )
    graph.add_node("postprocess", build_postprocess_node())

    graph.add_edge(START, "prepare_context")
    graph.add_edge("prepare_context", "call_model")
    graph.add_edge("call_model", "postprocess")
    graph.add_edge("postprocess", END)

    return graph.compile()

