from __future__ import annotations

from fastapi import Request

from gateway.platforms.webhook.runtime import WebhookRoute, WebhookRuntime
from shared_types.protocol import StateStore


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


async def _handle_mood(_: Request, state_store: StateStore) -> dict[str, object]:
    mood = await state_store.get_mood()
    return {
        "mood": mood.as_dict(),
    }


async def _handle_life_notes(
    _: Request,
    state_store: StateStore,
) -> dict[str, object]:
    notes = await state_store.get_life_notes()
    return {
        "life_notes": [note.to_dict() for note in notes],
    }


async def _handle_history(
    _: Request,
    state_store: StateStore,
) -> dict[str, object]:
    history = await state_store.get_history()
    return {
        "count": len(history),
        "history": history.as_dict(),
    }
