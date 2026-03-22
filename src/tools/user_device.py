from __future__ import annotations

from typing import Any

import httpx
from langchain_core.tools import BaseTool
from pydantic import BaseModel, PrivateAttr

from src.core.circuit_breaker import CircuitBreaker, CircuitOpenError
from src.shared_types.protocol import StateStore
from src.shared_types.tool_schemas import UserDeviceToolArgs


class UserDeviceTool(BaseTool):
    name: str = "user_device_tool"
    description: str = (
        "Controls user device actions like location, flashlight, or find phone."
    )
    args_schema: type[BaseModel] = UserDeviceToolArgs

    _state_store: StateStore = PrivateAttr()
    _join_api_key: str | None = PrivateAttr(default=None)
    _join_device_id: str | None = PrivateAttr(default=None)
    _circuit: CircuitBreaker = PrivateAttr()

    def __init__(
        self,
        *,
        state_store: StateStore,
        join_api_key: str | None,
        join_device_id: str | None,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
    ) -> None:
        super().__init__()
        self._state_store = state_store
        self._join_api_key = join_api_key
        self._join_device_id = join_device_id
        self._circuit = CircuitBreaker(
            name="join_api",
            failure_threshold=failure_threshold,
            recovery_timeout_seconds=recovery_timeout_seconds,
        )

    async def _arun(
        self,
        command: str = "user_location",
        content: str | None = None,
        state: dict[str, Any] | None = None,
    ) -> str:
        del state
        normalized = str(command or "user_location").strip().lower()

        if normalized == "user_location":
            location = await self._state_store.get_live_location()
            return (
                f"User location is {location.latitude:.5f}, {location.longitude:.5f}."
            )

        if not self._join_api_key or not self._join_device_id:
            return "Join integration is not configured."

        tasker_text = {
            "toggle_flashlight": "flash_command",
            "find_phone": "fmp_command",
            "speak_to_user": f"say={str(content or '').strip()}",
        }.get(normalized)
        if not tasker_text:
            return f"Unsupported device command: {normalized}."

        url = "https://joinjoaomgcd.appspot.com/_ah/api/messaging/v1/sendPush"
        params = {
            "apikey": self._join_api_key,
            "deviceId": self._join_device_id,
            "text": tasker_text,
        }

        try:
            response = await self._circuit.call(
                lambda: self._send_join_request(url, params),
                fallback=None,
            )
        except CircuitOpenError:
            return "Join service temporarily unavailable (circuit open). Try again in a moment."

        if response is None:
            return "Failed to send device command (service unavailable)."
        if response.status_code == 200:
            return f"Device command sent: {normalized}."
        return f"Failed to send device command ({response.status_code})."

    async def _send_join_request(
        self,
        url: str,
        params: dict[str, Any],
    ) -> httpx.Response | None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                return await client.get(url, params=params)
        except httpx.HTTPError:
            return None

    def _run(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError("Use async execution for user_device_tool.")
