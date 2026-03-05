from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from shared_types.types import AgentGraphState


def build_finalize_node(
    history_store: dict[str, list[BaseMessage]],
    max_history_messages: int,
):
    async def finalize_node(state: AgentGraphState) -> dict[str, Any]:
        thread_id = str(state.get("thread_id") or "global")
        user_text = str(state.get("user_text") or "").strip()
        reply_text = str(state.get("reply_text") or "").strip()

        history = list(history_store.get(thread_id, []))
        if user_text and reply_text:
            history = [
                *history, HumanMessage(content=user_text), AIMessage(content=reply_text)]
            history_store[thread_id] = history[-max_history_messages:]

        return {"reply_text": reply_text}

    return finalize_node
