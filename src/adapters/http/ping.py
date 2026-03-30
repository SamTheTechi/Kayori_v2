from __future__ import annotations

from fastapi import Request

from src.adapters.runtime.webhook_runtime import WebhookRoute, WebhookRuntime


def register_ping_routes(runtime: WebhookRuntime) -> None:
    runtime.add_route(
        WebhookRoute(
            path="/api/ping",
            methods=("GET",),
            endpoint=_handle_ping,
            require_bearer_auth=True,
            name="api-ping",
        )
    )


async def _handle_ping(_: Request) -> dict[str, bool]:
    return {"ok": True}
