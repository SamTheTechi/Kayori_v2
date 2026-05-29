"""Tool registry with auto-discovery.

Each tool module calls `registry.register(...)` at module level.
`discover()` auto-imports all tool modules, triggering their registration.
`get_tools(**deps)` instantiates every tool whose availability checks pass.
"""
from __future__ import annotations

import importlib
import os
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolDef:
    name: str
    description: str
    toolset: str = "default"
    requires_env: list[str] = field(default_factory=list)

    def is_available(self) -> bool:
        return all(bool(os.getenv(k)) for k in self.requires_env)


class _ToolRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[ToolDef, Callable[..., Any]]] = {}
        self._discovered = False

    def register(
        self,
        name: str,
        *,
        description: str,
        factory: Callable[..., Any],
        toolset: str = "default",
        requires_env: list[str] | None = None,
    ) -> None:
        meta = ToolDef(
            name=name,
            description=description,
            toolset=toolset,
            requires_env=requires_env or [],
        )
        self._entries[name] = (meta, factory)

    def discover(self) -> None:
        if self._discovered:
            return
        import tools as pkg
        for mod in pkgutil.iter_modules(pkg.__path__):
            if mod.name != "__init__":
                importlib.import_module(f"tools.{mod.name}")
        self._discovered = True

    def get_tools(self, **deps: Any) -> list:
        tools: list = []
        for name, (meta, factory) in self._entries.items():
            if not meta.is_available():
                continue
            try:
                result = factory(**deps)
            except Exception:
                continue
            if result is None:
                continue
            if isinstance(result, list):
                tools.extend(result)
            else:
                tools.append(result)
        return tools

    @property
    def toolsets(self) -> set[str]:
        return {meta.toolset for meta, _ in self._entries.values()}

    def list_tools(self, toolset: str | None = None) -> list[ToolDef]:
        if toolset is None:
            return [meta for meta, _ in self._entries.values()]
        return [
            meta
            for meta, _ in self._entries.values()
            if meta.toolset == toolset
        ]


registry = _ToolRegistry()
