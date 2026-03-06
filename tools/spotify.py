from __future__ import annotations

import asyncio
from os import getenv
from typing import Any

import spotipy
from langchain_core.tools import BaseTool
from pydantic import BaseModel, PrivateAttr
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth

from tools.schemas import SpotifyToolArgs

SPOTIFY_TAG = "[spotify_tool]"
NO_DEVICE_MESSAGE = "No active Spotify device found."
MISSING_CREDENTIALS_MESSAGE = (
    "Spotify credentials are missing. Set SPOTIFY_CLIENT_ID, "
    "SPOTIFY_CLIENT_SECRET, and SPOTIFY_REDIRECT_URI."
)
SUPPORTED_COMMANDS = (
    "play",
    "play_track",
    "pause",
    "resume",
    "next",
    "previous",
    "now_playing",
    "volume_up",
    "volume_down",
)


class SpotifyTool(BaseTool):
    name: str = "spotify_tool"
    description: str = (
        "Control Spotify playback. Use play to resume, play_track with a query "
        "to queue and jump to a song, now_playing for the current track, and "
        "volume_up/volume_down for relative volume changes."
    )
    args_schema: type[BaseModel] = SpotifyToolArgs

    _client: spotipy.Spotify | None = PrivateAttr(default=None)

    def __init__(self, *, enabled: bool | None = None) -> None:
        # Backward-compatible with the current app wiring. Tool enablement should
        # be controlled by whether this tool is added to the tools list at all.
        del enabled
        super().__init__()

    async def _arun(
        self,
        command: str = "play",
        query: str | None = None,
        step: int = 10,
        state: dict[str, Any] | None = None,
    ) -> str:
        del state

        normalized = _normalize_command(command)
        cleaned_query = _clean_query(query)
        step_value = _normalize_step(step)

        if normalized is None:
            print(f"{SPOTIFY_TAG} unsupported_command raw={command!r}")
            return _unsupported_command_message(command)

        print(
            f"{SPOTIFY_TAG} command_start command={normalized} "
            f"has_query={bool(cleaned_query)} step={step_value}"
        )

        if normalized == "play_track" and not cleaned_query:
            return "play_track requires a non-empty query."

        try:
            client = self._build_client()
        except RuntimeError as exc:
            print(f"{SPOTIFY_TAG} client_error err={exc}")
            return str(exc)
        except Exception as exc:
            print(f"{SPOTIFY_TAG} client_error err={exc}")
            return "Failed to initialize Spotify client."

        try:
            if normalized == "play":
                result = await _resume_playback(client)
            elif normalized == "play_track":
                result = await _play_track(client, query=cleaned_query or "")
            elif normalized == "pause":
                result = await _pause_playback(client)
            elif normalized == "next":
                result = await _skip_to_next(client)
            elif normalized == "previous":
                result = await _skip_to_previous(client)
            elif normalized == "now_playing":
                result = await _now_playing(client)
            elif normalized == "volume_up":
                result = await _adjust_volume(client, direction=1, step=step_value)
            elif normalized == "volume_down":
                result = await _adjust_volume(client, direction=-1, step=step_value)
            else:
                return _unsupported_command_message(normalized)
        except SpotifyException as exc:
            print(
                f"{SPOTIFY_TAG} spotify_exception command={normalized} "
                f"status={getattr(exc, 'http_status', None)} err={exc}"
            )
            return _format_spotify_error(exc)
        except Exception as exc:
            print(f"{SPOTIFY_TAG} execute_error command={normalized} err={exc}")
            return "Spotify request failed."

        print(f"{SPOTIFY_TAG} command_ok command={normalized}")
        return result

    def _run(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError("Use async execution for spotify_tool.")

    def _build_client(self) -> spotipy.Spotify:
        if self._client is not None:
            return self._client

        client_id = str(getenv("SPOTIFY_CLIENT_ID", "")).strip()
        client_secret = str(getenv("SPOTIFY_CLIENT_SECRET", "")).strip()
        redirect_uri = str(
            getenv("SPOTIFY_REDIRECT_URI") or getenv("SPOTIFY_REDIRECT") or ""
        ).strip()
        cache_path = str(
            getenv("SPOTIFY_CACHE_PATH", ".spotify_token_cache.json")
        ).strip()

        if redirect_uri.startswith("http://localhost:"):
            redirect_uri = redirect_uri.replace(
                "http://localhost:", "http://127.0.0.1:", 1
            )

        if not client_id or not client_secret or not redirect_uri:
            raise RuntimeError(MISSING_CREDENTIALS_MESSAGE)

        oauth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=(
                "user-modify-playback-state user-read-playback-state "
                "user-read-currently-playing user-top-read user-library-read "
                "user-read-recently-played"
            ),
            open_browser=True,
            cache_path=cache_path,
        )
        self._client = spotipy.Spotify(auth_manager=oauth)
        return self._client


def _normalize_command(command: str) -> str | None:
    value = str(command or "").strip().lower()
    aliases = {
        "play": "play",
        "resume": "play",
        "play_track": "play_track",
        "pause": "pause",
        "next": "next",
        "previous": "previous",
        "now_playing": "now_playing",
        "volume_up": "volume_up",
        "volume_down": "volume_down",
    }
    return aliases.get(value)


def _normalize_step(step: int | None) -> int:
    if step is None:
        return 10
    try:
        parsed = int(step)
    except Exception:
        return 10
    return max(1, min(25, parsed))


def _clean_query(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _unsupported_command_message(command: object) -> str:
    supported = ", ".join(SUPPORTED_COMMANDS)
    return f"Unsupported Spotify command '{command}'. Supported commands: {supported}."


def _format_spotify_error(exc: SpotifyException) -> str:
    status = getattr(exc, "http_status", None)
    if status == 401:
        return "Spotify authorization failed. Re-authenticate the Spotify app."
    if status == 403:
        return "Spotify account or device does not allow this action."
    if status == 404:
        return NO_DEVICE_MESSAGE
    if status == 429:
        return "Spotify rate limit reached. Try again shortly."
    reason = str(getattr(exc, "msg", "") or str(exc)).strip()
    return f"Spotify API error ({status or 'unknown'}): {reason}"


def _track_label(track: dict[str, Any]) -> str:
    name = str(track.get("name") or "Unknown track").strip()
    artists = track.get("artists") or []
    artist_names = ", ".join(
        str(item.get("name") or "").strip()
        for item in artists
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    )
    if artist_names:
        return f"{name} by {artist_names}"
    return name


def _first_playable_track(items: list[Any]) -> dict[str, Any] | None:
    for item in items:
        if not isinstance(item, dict):
            continue
        uri = str(item.get("uri") or "").strip()
        if uri:
            return item
    return None


def _get_active_device(playback: dict[str, Any] | None) -> dict[str, Any] | None:
    device = (playback or {}).get("device")
    return device if isinstance(device, dict) else None


def _device_volume(payload: dict[str, Any] | None) -> int | None:
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("volume_percent"), int):
        return max(0, min(100, int(payload["volume_percent"])))
    device = payload.get("device")
    if isinstance(device, dict) and isinstance(device.get("volume_percent"), int):
        return max(0, min(100, int(device["volume_percent"])))
    return None


async def _get_current_playback(client: spotipy.Spotify) -> dict[str, Any] | None:
    payload = await asyncio.to_thread(client.current_playback)
    return payload if isinstance(payload, dict) else None


async def _get_available_device(client: spotipy.Spotify) -> dict[str, Any] | None:
    payload = await asyncio.to_thread(client.devices)
    devices = list((payload or {}).get("devices") or [])
    active_device = next(
        (
            device
            for device in devices
            if isinstance(device, dict) and bool(device.get("is_active"))
        ),
        None,
    )
    if isinstance(active_device, dict):
        return active_device

    for device in devices:
        if isinstance(device, dict):
            return device
    return None


async def _resolve_target_device(
    client: spotipy.Spotify,
    playback: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    active_device = _get_active_device(playback)
    if active_device is not None:
        return active_device
    return await _get_available_device(client)


def _device_id(device: dict[str, Any] | None) -> str | None:
    if not isinstance(device, dict):
        return None
    value = str(device.get("id") or "").strip()
    return value or None


async def _resume_playback(client: spotipy.Spotify) -> str:
    playback = await _get_current_playback(client)
    if playback and bool(playback.get("is_playing")):
        return "Playback is already active."

    device = await _resolve_target_device(client, playback)
    if device is None:
        return NO_DEVICE_MESSAGE

    device_id = _device_id(device)
    kwargs: dict[str, Any] = {}
    if device_id:
        kwargs["device_id"] = device_id
    await asyncio.to_thread(client.start_playback, **kwargs)
    return "Playback resumed."


async def _pause_playback(client: spotipy.Spotify) -> str:
    playback = await _get_current_playback(client)
    if playback is not None and not bool(playback.get("is_playing")):
        return "Playback is already paused."

    device = await _resolve_target_device(client, playback)
    if device is None:
        return NO_DEVICE_MESSAGE

    device_id = _device_id(device)
    kwargs: dict[str, Any] = {}
    if device_id:
        kwargs["device_id"] = device_id
    await asyncio.to_thread(client.pause_playback, **kwargs)
    return "Playback paused."


async def _skip_to_next(client: spotipy.Spotify) -> str:
    playback = await _get_current_playback(client)
    device = await _resolve_target_device(client, playback)
    if device is None:
        return NO_DEVICE_MESSAGE

    device_id = _device_id(device)
    kwargs: dict[str, Any] = {}
    if device_id:
        kwargs["device_id"] = device_id
    await asyncio.to_thread(client.next_track, **kwargs)
    return "Skipped to next track."


async def _skip_to_previous(client: spotipy.Spotify) -> str:
    playback = await _get_current_playback(client)
    device = await _resolve_target_device(client, playback)
    if device is None:
        return NO_DEVICE_MESSAGE

    device_id = _device_id(device)
    kwargs: dict[str, Any] = {}
    if device_id:
        kwargs["device_id"] = device_id
    await asyncio.to_thread(client.previous_track, **kwargs)
    return "Went to previous track."


async def _now_playing(client: spotipy.Spotify) -> str:
    playback = await _get_current_playback(client)
    if not playback:
        return "No active playback right now."

    item = playback.get("item")
    if not isinstance(item, dict):
        return "No active playback right now."

    device_name = str((_get_active_device(playback) or {}).get("name") or "").strip()
    status = "playing" if bool(playback.get("is_playing")) else "paused"
    suffix = f" on {device_name}" if device_name else ""
    return f"Now {status}: {_track_label(item)}{suffix}."


async def _adjust_volume(
    client: spotipy.Spotify,
    *,
    direction: int,
    step: int,
) -> str:
    playback = await _get_current_playback(client)
    device = await _resolve_target_device(client, playback)
    if device is None:
        return NO_DEVICE_MESSAGE

    current = _device_volume(playback)
    if current is None:
        current = _device_volume(device)
    if current is None:
        return NO_DEVICE_MESSAGE

    next_value = max(0, min(100, current + (step * direction)))
    if next_value == current:
        if direction > 0:
            return "Volume is already at maximum."
        return "Volume is already at minimum."

    device_id = _device_id(device)
    kwargs: dict[str, Any] = {}
    if device_id:
        kwargs["device_id"] = device_id
    await asyncio.to_thread(client.volume, next_value, **kwargs)

    if direction > 0:
        return f"Volume increased from {current}% to {next_value}%."
    return f"Volume decreased from {current}% to {next_value}%."


async def _play_track(client: spotipy.Spotify, *, query: str) -> str:
    track = await _match_track(client, query=query)
    if track is None:
        return f"No Spotify match found for '{query}'."

    playback = await _get_current_playback(client)
    device = await _resolve_target_device(client, playback)
    if device is None:
        return NO_DEVICE_MESSAGE

    uri = str(track.get("uri") or "").strip()
    if not uri:
        return f"No Spotify match found for '{query}'."

    device_id = _device_id(device)
    label = _track_label(track)

    if playback is not None:
        queue_kwargs: dict[str, Any] = {}
        next_kwargs: dict[str, Any] = {}
        start_kwargs: dict[str, Any] = {}
        if device_id:
            queue_kwargs["device_id"] = device_id
            next_kwargs["device_id"] = device_id
            start_kwargs["device_id"] = device_id

        await asyncio.to_thread(client.add_to_queue, uri, **queue_kwargs)
        await asyncio.to_thread(client.next_track, **next_kwargs)
        if not bool(playback.get("is_playing")):
            await asyncio.to_thread(client.start_playback, **start_kwargs)
        return f"Queued and playing: {label}."

    start_kwargs = {"uris": [uri]}
    if device_id:
        start_kwargs["device_id"] = device_id
    await asyncio.to_thread(client.start_playback, **start_kwargs)
    return f"Playing: {label}."


async def _match_track(
    client: spotipy.Spotify,
    *,
    query: str,
) -> dict[str, Any] | None:
    print(f"{SPOTIFY_TAG} search_tracks query={query!r}")
    track_search = await asyncio.to_thread(
        client.search,
        q=query,
        type="track",
        limit=5,
    )
    track_items = list(((track_search or {}).get("tracks") or {}).get("items") or [])
    track = _first_playable_track(track_items)
    if track is not None:
        return track

    print(f"{SPOTIFY_TAG} search_artists query={query!r}")
    artist_search = await asyncio.to_thread(
        client.search,
        q=query,
        type="artist",
        limit=3,
    )
    artist_items = list(
        ((artist_search or {}).get("artists") or {}).get("items") or []
    )
    first_artist = artist_items[0] if artist_items else None
    artist_id = str((first_artist or {}).get("id") or "").strip()
    if not artist_id:
        return None

    top_payload = await asyncio.to_thread(
        client.artist_top_tracks,
        artist_id,
        country="US",
    )
    top_tracks = list((top_payload or {}).get("tracks") or [])
    return _first_playable_track(top_tracks)
