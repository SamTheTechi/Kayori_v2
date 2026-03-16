from __future__ import annotations

import asyncio
import json
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class JsonlLogger:
    """Simple async-safe JSONL logger with bounded line retention."""

    def __init__(
        self,
        path: str | Path = "logs/app.jsonl",
        *,
        enabled: bool = True,
        max_lines: int = 5000,
        include_traceback: bool = True,
        name: str = "app",
    ) -> None:
        self.path = Path(path)
        self.enabled = enabled
        self.max_lines = max(1, int(max_lines))
        self.include_traceback = include_traceback
        self.name = str(name or "app").strip() or "app"
        self._lock = asyncio.Lock()

    def bind(self, name: str) -> JsonlLogger:
        return JsonlLogger(
            path=self.path,
            enabled=self.enabled,
            max_lines=self.max_lines,
            include_traceback=self.include_traceback,
            name=name,
        )

    async def debug(
        self,
        event: str,
        message: str = "",
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        await self._write_event(
            level="debug",
            event=event,
            message=message,
            context=context,
        )

    async def info(
        self,
        event: str,
        message: str = "",
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        await self._write_event(
            level="info",
            event=event,
            message=message,
            context=context,
        )

    async def warning(
        self,
        event: str,
        message: str = "",
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        await self._write_event(
            level="warning",
            event=event,
            message=message,
            context=context,
        )

    async def error(
        self,
        event: str,
        message: str = "",
        *,
        context: dict[str, Any] | None = None,
        error: BaseException | str | None = None,
    ) -> None:
        await self._write_event(
            level="error",
            event=event,
            message=message,
            context=context,
            error=error,
        )

    async def exception(
        self,
        event: str,
        message: str = "",
        *,
        context: dict[str, Any] | None = None,
        error: BaseException | str | None = None,
    ) -> None:
        await self._write_event(
            level="error",
            event=event,
            message=message,
            context=context,
            error=error,
            include_traceback=True,
        )

    async def _write_event(
        self,
        *,
        level: str,
        event: str,
        message: str,
        context: dict[str, Any] | None = None,
        error: BaseException | str | None = None,
        include_traceback: bool = False,
    ) -> None:
        if not self.enabled:
            return

        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": level,
            "logger": self.name,
            "event": str(event or "log_event").strip() or "log_event",
            "message": str(message or "").strip(),
            "context": _json_safe(context or {}),
        }

        error_payload = _error_payload(error)
        if error_payload is not None:
            payload["error"] = error_payload

        should_include_traceback = include_traceback and self.include_traceback
        if should_include_traceback:
            trace = traceback.format_exc().strip()
            if trace and trace != "NoneType: None":
                payload["traceback"] = trace

        async with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(
                    payload, ensure_ascii=True, sort_keys=True))
                handle.write("\n")
            self._trim_old_lines()

    def _trim_old_lines(self) -> None:
        if self.max_lines <= 0 or not self.path.exists():
            return

        lines = self.path.read_text(encoding="utf-8").splitlines()
        if len(lines) <= self.max_lines:
            return

        kept = lines[-self.max_lines:]
        self.path.write_text("\n".join(kept) + "\n", encoding="utf-8")


def _error_payload(error: BaseException | str | None) -> dict[str, Any] | None:
    if error is None:
        return None
    if isinstance(error, BaseException):
        return {
            "type": error.__class__.__name__,
            "message": str(error).strip(),
        }
    return {
        "type": "Error",
        "message": str(error).strip(),
    }


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=True, sort_keys=True)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(key): _json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(item) for item in value]
        return str(value)


_default_logger = JsonlLogger()
_named_loggers: dict[str, JsonlLogger] = {}


def get_logger(name: str) -> JsonlLogger:
    key = str(name or "app").strip() or "app"
    logger = _named_loggers.get(key)
    if logger is not None:
        return logger
    logger = _default_logger.bind(key)
    _named_loggers[key] = logger
    return logger
