from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, Response

from src.adapters.runtime.webhook_runtime import WebhookRoute, WebhookRuntime

DASHBOARD_DIR = Path(__file__).resolve().parents[2] / "dashboard"
DASHBOARD_PATH = DASHBOARD_DIR / "index.html"
STYLES_PATH = DASHBOARD_DIR / "styles.css"
APP_JS_PATH = DASHBOARD_DIR / "app.js"


def register_dashboard_routes(runtime: WebhookRuntime) -> None:
    runtime.add_route(
        WebhookRoute(
            path="/dashboard",
            methods=("GET",),
            endpoint=_handle_dashboard,
            name="dashboard",
        )
    )
    runtime.add_route(
        WebhookRoute(
            path="/dashboard/styles.css",
            methods=("GET",),
            endpoint=_handle_dashboard_css,
            name="dashboard-css",
        )
    )
    runtime.add_route(
        WebhookRoute(
            path="/dashboard/app.js",
            methods=("GET",),
            endpoint=_handle_dashboard_js,
            name="dashboard-js",
        )
    )


async def _handle_dashboard(_: Request) -> HTMLResponse:
    return HTMLResponse(DASHBOARD_PATH.read_text(encoding="utf-8"))


async def _handle_dashboard_css(_: Request) -> Response:
    return Response(
        content=STYLES_PATH.read_text(encoding="utf-8"),
        media_type="text/css",
    )


async def _handle_dashboard_js(_: Request) -> Response:
    return Response(
        content=APP_JS_PATH.read_text(encoding="utf-8"),
        media_type="application/javascript",
    )
