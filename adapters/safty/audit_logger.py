from __future__ import annotations

import asyncio
import json
from pathlib import Path

from shared_types.types import ToolAuditEvent


class JsonlAuditLogger:
    """Append-only JSONL audit log for tool actions."""

    def __init__(
        self,
        path: str | Path,
        enabled: bool = True,
        max_lines: int = 1000,
    ):
        self.path = Path(path)
        self.enabled = enabled
        self.max_lines = max(1, int(max_lines))
        self._lock = asyncio.Lock()

    async def log_tool_event(self, event: ToolAuditEvent) -> None:
        await self._write_event(event)

    async def log_skill_event(self, event: ToolAuditEvent) -> None:
        await self._write_event(event)

    async def _write_event(self, event: ToolAuditEvent) -> None:
        if not self.enabled:
            return
        async with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(dict(event),
                             ensure_ascii=True, sort_keys=True))
                handle.write("\n")
            self._trim_old_lines()

    def _trim_old_lines(self) -> None:
        if self.max_lines <= 0 or not self.path.exists():
            return

        lines = self.path.read_text(encoding="utf-8").splitlines()
        if len(lines) <= self.max_lines:
            return

        kept = lines[-self.max_lines:]
        payload = "\n".join(kept) + "\n"
        self.path.write_text(payload, encoding="utf-8")
