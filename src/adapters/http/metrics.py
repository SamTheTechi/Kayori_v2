from __future__ import annotations

import os

from fastapi import Request

from src.adapters.runtime.webhook_runtime import WebhookRoute, WebhookRuntime
from src.shared_types.protocol import StateStore


def register_metrics_routes(runtime: WebhookRuntime, state_store: StateStore) -> None:
    runtime.add_route(
        WebhookRoute(
            path="/api/metrics/mood",
            methods=("GET",),
            endpoint=lambda request: _handle_mood(request, state_store),
            require_bearer_auth=True,
            name="api-metrics-mood",
        )
    )
    runtime.add_route(
        WebhookRoute(
            path="/api/metrics/life-notes",
            methods=("GET",),
            endpoint=lambda request: _handle_life_notes(request, state_store),
            require_bearer_auth=True,
            name="api-metrics-life-notes",
        )
    )
    runtime.add_route(
        WebhookRoute(
            path="/api/metrics/history",
            methods=("GET",),
            endpoint=lambda request: _handle_history(request, state_store),
            require_bearer_auth=True,
            name="api-metrics-history",
        )
    )
    runtime.add_route(
        WebhookRoute(
            path="/api/metrics/threads",
            methods=("GET",),
            endpoint=lambda request: _handle_threads(request, state_store),
            require_bearer_auth=True,
            name="api-metrics-threads",
        )
    )


async def _handle_mood(request: Request, state_store: StateStore) -> dict[str, object]:
    thread_id = _thread_id(request)
    mood = await state_store.get_mood(thread_id)
    return {
        "thread_id": thread_id,
        "mood": mood.as_dict(),
    }


async def _handle_life_notes(
    request: Request,
    state_store: StateStore,
) -> dict[str, object]:
    thread_id = _thread_id(request)
    notes = await state_store.get_life_notes(thread_id)
    return {
        "thread_id": thread_id,
        "life_notes": [note.to_dict() for note in notes],
    }


async def _handle_history(
    request: Request,
    state_store: StateStore,
) -> dict[str, object]:
    thread_id = _thread_id(request)
    history = await state_store.get_history(thread_id)
    return {
        "thread_id": thread_id,
        "count": len(history),
        "history": history.as_dict(),
    }


async def _handle_threads(
    _: Request,
    state_store: StateStore,
) -> dict[str, object]:
    threads = await state_store.list_threads()
    return {
        "count": len(threads),
        "threads": threads,
    }


def _thread_id(request: Request) -> str:
    return (
        str(request.query_params.get("thread_id") or "").strip()
        or str(os.getenv("FORCE_THREAD_ID", "")).strip()
        or "global"
    )
