from __future__ import annotations

import asyncio
import json
from pathlib import Path

from shared_types.types import ToolAuditEvent


class JsonlAuditLogger:
    """Append-only JSONL audit log for tool actions with batched compaction."""

    def __init__(
        self,
        path: str | Path,
        enabled: bool = True,
        max_lines: int = 1000,
        trim_batch_lines: int = 250,
    ):
        self.path = Path(path)
        self.enabled = enabled
        self.max_lines = max(1, int(max_lines))
        self.trim_batch_lines = max(1, int(trim_batch_lines))
        self._lock = asyncio.Lock()
        self._line_count: int | None = None

    async def log_tool_event(self, event: ToolAuditEvent) -> None:
        await self._write_event(event)

    async def log_skill_event(self, event: ToolAuditEvent) -> None:
        await self._write_event(event)

    async def _write_event(self, event: ToolAuditEvent) -> None:
        if not self.enabled:
            return
        async with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._line_count = self._current_line_count()
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(dict(event), ensure_ascii=True, sort_keys=True))
                handle.write("\n")
            self._line_count += 1
            if self._line_count > self.max_lines:
                self._compact_file()

    def _current_line_count(self) -> int:
        if self._line_count is not None:
            return self._line_count
        if not self.path.exists():
            return 0
        with self.path.open("r", encoding="utf-8") as handle:
            return sum(1 for _ in handle)

    def _compact_file(self) -> None:
        if not self.path.exists():
            self._line_count = 0
            return

        keep_lines = max(1, self.max_lines - self.trim_batch_lines)
        with self.path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()

        kept = lines[-keep_lines:]
        with self.path.open("w", encoding="utf-8") as handle:
            handle.writelines(kept)
        self._line_count = len(kept)
