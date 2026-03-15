from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status

from logger import get_logger

WebhookEndpoint = Callable[[Request], Awaitable[Any]]
logger = get_logger("runtime.webhook")


@dataclass(slots=True)
class WebhookRoute:
    path: str
    methods: tuple[str, ...]
    endpoint: WebhookEndpoint
    require_bearer_auth: bool = False
    name: str | None = None


@dataclass(slots=True)
class WebhookRuntime:
    host: str = "127.0.0.1"
    port: int = 8080
    bearer_token: str | None = None
    response_timeout_seconds: float = 30.0
    name: str = "webhook-runtime"

    _app: FastAPI = field(init=False, repr=False)
    _routes: list[WebhookRoute] = field(
        default_factory=list, init=False, repr=False)
    _route_keys: set[tuple[str, tuple[str, ...]]] = field(
        default_factory=set, init=False, repr=False
    )
    _server: uvicorn.Server | None = field(
        default=None, init=False, repr=False)
    _server_task: asyncio.Task[None] | None = field(
        default=None, init=False, repr=False
    )
    _started: bool = field(default=False, init=False, repr=False)
    _pending_responses: dict[str, asyncio.Future[dict[str, Any]]] = field(
        default_factory=dict, init=False, repr=False
    )

    def __post_init__(self) -> None:
        self._app = FastAPI(title="Kayori Webhook Runtime")
        self._register_default_routes()

    @property
    def app(self) -> FastAPI:
        return self._app

    def add_route(self, route: WebhookRoute) -> None:
        methods = tuple(sorted({item.upper() for item in route.methods}))
        if not methods:
            raise ValueError("route.methods must not be empty")

        key = (route.path, methods)
        if key in self._route_keys:
            raise ValueError(f"Duplicate webhook route: {
                             route.path} {methods}")
        if self._started:
            raise RuntimeError(
                "Cannot register routes after webhook runtime start.")

        async def wrapped_endpoint(request: Request) -> Any:
            if route.require_bearer_auth:
                self._verify_bearer_token(request)
            return await route.endpoint(request)

        self._app.add_api_route(
            route.path,
            wrapped_endpoint,
            methods=list(methods),
            name=route.name,
        )
        self._routes.append(
            WebhookRoute(
                path=route.path,
                methods=methods,
                endpoint=route.endpoint,
                require_bearer_auth=route.require_bearer_auth,
                name=route.name,
            )
        )
        self._route_keys.add(key)

    async def start(self) -> None:
        if self._started:
            return

        config = uvicorn.Config(
            app=self._app,
            host=self.host,
            port=self.port,
            log_level="info",
            lifespan="on",
        )
        self._server = uvicorn.Server(config)
        self._server_task = asyncio.create_task(
            self._server.serve(),
            name="webhook-runtime",
        )
        self._started = True
        await self._wait_until_started()
        await logger.info(
            "webhook_runtime_started",
            "Webhook runtime listening.",
            context={"host": self.host, "port": self.port},
        )

    async def stop(self) -> None:
        if not self._started:
            return

        server = self._server
        task = self._server_task
        self._started = False
        self._server = None
        self._server_task = None

        if server is not None:
            server.should_exit = True
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        for correlation_id in list(self._pending_responses):
            self.discard_response(correlation_id)

    def create_pending_response(self) -> str:
        correlation_id = uuid4().hex
        loop = asyncio.get_running_loop()
        self._pending_responses[correlation_id] = loop.create_future()
        return correlation_id

    async def wait_for_response(
        self,
        correlation_id: str,
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        future = self._pending_responses.get(correlation_id)
        if future is None:
            raise RuntimeError("Webhook response is not registered.")

        timeout = (
            self.response_timeout_seconds
            if timeout_seconds is None
            else float(timeout_seconds)
        )
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
        except TimeoutError as exc:
            self.discard_response(correlation_id)
            raise TimeoutError(
                f"Webhook response timed out after {timeout:.1f}s."
            ) from exc
        finally:
            self._pending_responses.pop(correlation_id, None)

    def resolve_response(self, correlation_id: str, payload: dict[str, Any]) -> bool:
        future = self._pending_responses.get(correlation_id)
        if future is None or future.done():
            return False
        future.set_result(payload)
        return True

    def fail_response(self, correlation_id: str, detail: str) -> bool:
        future = self._pending_responses.get(correlation_id)
        if future is None or future.done():
            return False
        future.set_exception(
            RuntimeError(str(detail).strip() or "Webhook response failed.")
        )
        return True

    def discard_response(self, correlation_id: str) -> None:
        future = self._pending_responses.pop(correlation_id, None)
        if future is not None and not future.done():
            future.cancel()

    def _verify_bearer_token(self, request: Request) -> None:
        expected = str(self.bearer_token or "").strip()
        if not expected:
            raise RuntimeError(
                "Webhook bearer auth is enabled but bearer_token is empty."
            )

        raw = str(request.headers.get("authorization", "")).strip()
        prefix = "Bearer "
        if not raw.startswith(prefix):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing bearer token.",
            )
        provided = raw[len(prefix):].strip()
        if provided != expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token.",
            )

    def _register_default_routes(self) -> None:
        async def health(_: Request) -> dict[str, bool]:
            return {"ok": True}

        async def list_routes(_: Request) -> dict[str, list[dict[str, Any]]]:
            return {
                "routes": [
                    {
                        "path": route.path,
                        "methods": list(route.methods),
                        "name": route.name,
                        "require_bearer_auth": route.require_bearer_auth,
                    }
                    for route in self._routes
                ]
            }

        self.add_route(
            WebhookRoute(
                path="/healthz",
                methods=("GET",),
                endpoint=health,
                name="healthz",
            )
        )
        self.add_route(
            WebhookRoute(
                path="/webhooks/routes",
                methods=("GET",),
                endpoint=list_routes,
                name="webhook-routes",
            )
        )

    async def _wait_until_started(self) -> None:
        server = self._server
        task = self._server_task
        if server is None or task is None:
            raise RuntimeError("Webhook runtime server was not initialized.")

        while not server.started:
            if task.done():
                exc = task.exception()
                raise RuntimeError("Webhook runtime failed to start.") from exc
            await asyncio.sleep(0.05)
