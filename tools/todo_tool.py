from __future__ import annotations

import time
import uuid
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, PrivateAttr

from shared_types.models import Todo
from shared_types.protocol import StateStore
from shared_types.tool_schemas import TodoToolArgs


class TodoTool(BaseTool):
    name: str = "todo_tool"
    description: str = "Manage a persistent todo list."
    args_schema: type[BaseModel] = TodoToolArgs

    _state_store: StateStore = PrivateAttr()

    def __init__(self, *, state_store: StateStore) -> None:
        super().__init__()
        self._state_store = state_store

    async def _arun(
        self,
        action: str = "list",
        title: str | None = None,
        description: str | None = None,
        todo_id: str | None = None,
        priority: int | None = None,
        state: dict[str, Any] | None = None,
    ) -> str:
        del state
        action = (action or "list").strip().lower()

        if action == "create":
            return await self._create(title or "", description, priority)
        if action == "list":
            return await self._list()
        if action == "complete":
            return await self._update_status(todo_id or "", "completed")
        if action == "delete":
            return await self._delete(todo_id or "")
        if action == "update":
            return await self._update(todo_id or "", title, description, priority)
        if action == "summary":
            return await self._summary()

        return f"Unknown action: {action}. Use create, list, complete, delete, update, or summary."

    async def _create(self, title: str, description: str | None, priority: int | None) -> str:
        if not title or not title.strip():
            return "Error: title is required for create."
        todo = Todo(
            id=uuid.uuid4().hex[:12],
            title=title.strip(),
            description=(description or "").strip(),
            priority=priority if priority is not None else 0,
            status="pending",
            created_at=time.time(),
            updated_at=time.time(),
        )
        await self._state_store.add_todo(todo)
        return f"Created todo [{todo.id}]: {todo.title}"

    async def _list(self) -> str:
        todos = await self._state_store.get_todos()
        if not todos:
            return "No todos yet."
        lines = [f"[{t.status}] {t.id} {t.title}" for t in todos]
        return "\n".join(lines)

    async def _update_status(self, todo_id: str, status: str) -> str:
        if not todo_id:
            return "Error: todo_id is required."
        await self._state_store.update_todo(todo_id, status=status)
        return f"Todo {todo_id} marked as {status}."

    async def _delete(self, todo_id: str) -> str:
        if not todo_id:
            return "Error: todo_id is required."
        await self._state_store.delete_todo(todo_id)
        return f"Deleted todo {todo_id}."

    async def _update(self, todo_id: str, title: str | None, description: str | None, priority: int | None) -> str:
        if not todo_id:
            return "Error: todo_id is required."
        updates: dict[str, Any] = {}
        if title:
            updates["title"] = title.strip()
        if description is not None:
            updates["description"] = description.strip()
        if priority is not None:
            updates["priority"] = priority
        if not updates:
            return "Nothing to update."
        await self._state_store.update_todo(todo_id, **updates)
        return f"Updated todo {todo_id}."

    async def _summary(self) -> str:
        todos = await self._state_store.get_todos()
        if not todos:
            return "No todos yet."
        total = len(todos)
        pending = sum(1 for t in todos if t.status == "pending")
        in_progress = sum(1 for t in todos if t.status == "in_progress")
        completed = sum(1 for t in todos if t.status == "completed")
        cancelled = sum(1 for t in todos if t.status == "cancelled")
        return (
            f"Todos: {total} total ({pending} pending, {in_progress} in progress, "
            f"{completed} completed, {cancelled} cancelled)."
        )

    def _run(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError("Use async execution for todo_tool.")


from tools import registry  # noqa: E402

registry.register(
    "todo_tool",
    description="Manage a persistent todo list.",
    toolset="utility",
    factory=lambda state_store=None, **kw: [TodoTool(state_store=state_store)] if state_store else [],
)
