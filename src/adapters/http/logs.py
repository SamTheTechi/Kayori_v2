from __future__ import annotations

import json
from pathlib import Path

from fastapi import Request

from src.adapters.runtime.webhook_runtime import WebhookRoute, WebhookRuntime

LOG_PATH = Path("logs/app.json")


def register_logs_routes(runtime: WebhookRuntime) -> None:
    runtime.add_route(
        WebhookRoute(
            path="/api/logs",
            methods=("GET",),
            endpoint=_handle_logs,
            require_bearer_auth=True,
            name="api-logs",
        )
    )


async def _handle_logs(request: Request) -> dict[str, object]:
    raw_limit = str(request.query_params.get("limit") or "").strip()
    raw_level = str(request.query_params.get("level") or "").strip().lower()

    try:
        limit = int(raw_limit) if raw_limit else 100
    except Exception:
        limit = 100
    limit = max(1, limit)

    if not LOG_PATH.exists():
        return {"count": 0, "logs": []}

    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    logs: list[dict[str, object]] = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if raw_level and str(item.get("level") or "").strip().lower() != raw_level:
            continue
        if isinstance(item, dict):
            logs.append(item)
        if len(logs) >= limit:
            break

    logs.reverse()
    return {
        "count": len(logs),
        "logs": logs,
    }
