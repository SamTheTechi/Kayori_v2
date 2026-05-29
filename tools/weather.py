from __future__ import annotations

from os import getenv
from typing import Any

import httpx
from langchain_core.tools import BaseTool
from pydantic import BaseModel, PrivateAttr

from shared_types.helpers import clean_text, maybe_float
from shared_types.protocol import StateStore
from shared_types.tool_schemas import WeatherToolArgs


class WeatherTool(BaseTool):
    name: str = "weather_tool"
    description: str = "Get current weather for a location."
    args_schema: type[BaseModel] = WeatherToolArgs

    _state_store: StateStore = PrivateAttr()
    _api_key: str | None = PrivateAttr(default=None)

    def __init__(
        self,
        *,
        state_store: StateStore,
        api_key: str | None,
    ) -> None:
        super().__init__()
        self._state_store = state_store
        self._api_key = api_key

    async def _arun(
        self,
        unit: str = "c",
        location_override: str | None = None,
        state: dict[str, Any] | None = None,
    ) -> str:
        if not self._api_key:
            return "Weather tool is disabled because WEATHER_API_KEY is not configured."

        location_query = clean_text(location_override)
        if not location_query:
            location_query = _location_from_state(state)
        if not location_query:
            location_query = await _location_from_store(self._state_store)
        if not location_query:
            location_query = clean_text(getenv("WEATHER_DEFAULT_LOCATION", ""))
        if not location_query:
            return (
                "Weather location is unavailable. Provide location_override or set "
                "WEATHER_DEFAULT_LOCATION."
            )

        url = "https://api.weatherapi.com/v1/current.json"
        params = {"key": self._api_key, "q": location_query, "aqi": "no"}

        response = await self._fetch_weather(url, params)

        if response is None:
            return "Weather request failed. Try again shortly."

        if response.status_code != 200:
            return _weather_error_message(response)

        try:
            payload = response.json()
        except ValueError:
            return "Weather service returned an unreadable response."

        current = payload.get("current", {})
        condition = current.get("condition", {}).get("text", "Unknown")
        normalized_unit = (unit or "c").strip().lower()
        if normalized_unit == "f":
            temp = current.get("temp_f", "?")
            feels = current.get("feelslike_f", "?")
            unit_label = "F"
        else:
            temp = current.get("temp_c", "?")
            feels = current.get("feelslike_c", "?")
            unit_label = "C"
        humidity = current.get("humidity", "?")
        place = payload.get("location", {}).get("name") or location_query

        return (
            f"Current weather in {place}: {condition}, {temp}°{unit_label} "
            f"(feels {feels}°{unit_label}), humidity {humidity}%."
        )

    def _run(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError("Use async execution for weather_tool.")

    async def _fetch_weather(
        self,
        url: str,
        params: dict[str, Any],
    ) -> httpx.Response | None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
            return response
        except httpx.HTTPError:
            return None



def _coords_to_query(latitude: Any, longitude: Any) -> str | None:
    lat = maybe_float(latitude)
    lon = maybe_float(longitude)
    if lat is None or lon is None:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    if abs(lat) < 1e-9 and abs(lon) < 1e-9:
        return None
    return f"{lat},{lon}"


def _location_from_envelope_like(envelope: Any) -> str:
    if envelope is None:
        return ""

    metadata: dict[str, Any] = {}
    if isinstance(envelope, dict):
        metadata = dict(envelope.get("metadata") or {})
    else:
        metadata = dict(getattr(envelope, "metadata", {}) or {})

    for key in ("location_query", "weather_location", "location", "city", "address"):
        text = clean_text(metadata.get(key))
        if text:
            return text

    return (
        _coords_to_query(
            metadata.get("latitude", metadata.get("lat")),
            metadata.get("longitude", metadata.get("lon")),
        )
        or ""
    )


def _location_from_state(state: dict[str, Any] | None) -> str:
    payload = dict(state or {})

    for key in (
        "location_override",
        "location_query",
        "weather_location",
        "city",
        "address",
    ):
        text = clean_text(payload.get(key))
        if text:
            return text

    coords_query = _coords_to_query(
        payload.get("latitude", payload.get("lat")),
        payload.get("longitude", payload.get("lon")),
    )
    if coords_query:
        return coords_query

    envelope_query = _location_from_envelope_like(payload.get("envelope"))
    if envelope_query:
        return envelope_query

    return ""


async def _location_from_store(state_store: StateStore) -> str:
    live = await state_store.get_live_location()
    live_query = _coords_to_query(live.latitude, live.longitude)
    if live_query:
        return live_query

    pinned = await state_store.get_pinned_location()
    pinned_query = _coords_to_query(pinned.latitude, pinned.longitude)
    if pinned_query:
        return pinned_query

    return ""


def _weather_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = clean_text(error.get("message"))
            if message:
                return f"Weather API error ({response.status_code}): {message}"

    return f"Weather API error ({response.status_code})."


from tools import registry  # noqa: E402

registry.register(
    "weather_tool",
    description="Get current weather for a location.",
    toolset="utility",
    requires_env=["WEATHER_API_KEY"],
    factory=lambda state_store=None, api_key=None, **kw: (
        [WeatherTool(state_store=state_store, api_key=api_key)]
        if state_store is not None
        else []
    ),
)
