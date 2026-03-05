from __future__ import annotations

import asyncio
from os import getenv
import random
from typing import Any

import spotipy
from langchain_core.tools import BaseTool
from pydantic import BaseModel
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth

from tools.schemas import SpotifyToolArgs

SPOTIFY_TAG = "[spotify_tool]"


class SpotifyTool(BaseTool):
    name: str = "spotify_tool"
    description: str = (
        "Controls Spotify playback. Use command='play' with query to play a song/artist, "
        "or command='play' without query to auto-pick from recent/top listening."
    )
    args_schema: type[BaseModel] = SpotifyToolArgs

    def __init__(self, *, enabled: bool | None = None) -> None:
        del enabled
        super().__init__()

    async def _arun(
        self,
        command: str = "play_random",
        volume: int | None = None,
        query: str | None = None,
        state: dict[str, Any] | None = None,
    ) -> str:
        del state

        normalized = _normalize_command(str(command or "play_random"))
        if not normalized:
            print(f"{SPOTIFY_TAG} unsupported_command raw={command!r}")
            return "Unsupported Spotify command."

        parsed_volume = _parse_int(volume) if volume is not None else None
        cleaned_query = _clean_query(query)
        print(
            f"{SPOTIFY_TAG} command_start raw={
                command!r} normalized={normalized} "
            f"has_query={bool(cleaned_query)} volume={parsed_volume}"
        )
        if normalized == "volume" and parsed_volume is None:
            print(f"{SPOTIFY_TAG} invalid_volume_input raw={volume!r}")
            return "Volume command requires an integer in range 0-100."

        try:
            print(f"{SPOTIFY_TAG} build_client_start")
            client = self._build_client()
            print(f"{SPOTIFY_TAG} build_client_ok")
        except RuntimeError as exc:
            print(f"{SPOTIFY_TAG} build_client_runtime_error err={exc}")
            return str(exc)
        except Exception as exc:
            print(f"{SPOTIFY_TAG} build_client_error err={exc}")
            return f"Failed to initialize Spotify client: {exc}"

        try:
            print(f"{SPOTIFY_TAG} execute action={normalized}")
            if normalized == "play_pause":
                result = await _play_pause(client)
            elif normalized == "play":
                result = await _play(client, query=cleaned_query)
            elif normalized == "pause":
                result = await _pause(client)
            elif normalized == "next":
                result = await _next_track(client)
            elif normalized == "previous":
                result = await _previous_track(client)
            elif normalized == "track_info":
                result = await _track_info(client)
            elif normalized == "volume":
                result = await _set_volume(client, parsed_volume or 0)
            elif normalized == "play_random":
                result = await _play_random(client)
            else:
                print(f"{SPOTIFY_TAG} unsupported_normalized normalized={
                      normalized}")
                return "Unsupported Spotify command."

            print(f"{SPOTIFY_TAG} execute_ok action={normalized}")
            return result
        except SpotifyException as exc:
            print(
                f"{SPOTIFY_TAG} spotify_exception action={normalized} "
                f"status={getattr(exc, 'http_status', None)} err={exc}"
            )
            return _format_spotify_error(exc)
        except Exception as exc:
            print(f"{SPOTIFY_TAG} execute_error action={normalized} err={exc}")
            return f"Spotify request failed: {exc}"

    def _run(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError("Use async execution for spotify_tool.")

    def _build_client(self) -> spotipy.Spotify:
        client_id = str(getenv("SPOTIFY_CLIENT_ID", "")).strip()
        client_secret = str(getenv("SPOTIFY_CLIENT_SECRET", "")).strip()
        redirect_uri = str(
            getenv("SPOTIFY_REDIRECT_URI") or getenv("SPOTIFY_REDIRECT") or ""
        ).strip()
        cache_path = str(
            getenv("SPOTIFY_CACHE_PATH", ".spotify_token_cache.json")
        ).strip()

        # Spotify is deprecating localhost redirects; normalize to loopback IP.
        if redirect_uri.startswith("http://localhost:"):
            redirect_uri = redirect_uri.replace(
                "http://localhost:", "http://127.0.0.1:", 1
            )
            print(f"{SPOTIFY_TAG} normalized_redirect_uri redirect_uri={
                  redirect_uri}")

        if not client_id or not client_secret or not redirect_uri:
            print(
                f"{SPOTIFY_TAG} missing_credentials "
                f"client_id={bool(client_id)} client_secret={
                    bool(client_secret)} "
                f"redirect_uri={bool(redirect_uri)}"
            )
            raise RuntimeError(
                "Spotify credentials are missing. Set SPOTIFY_CLIENT_ID, "
                "SPOTIFY_CLIENT_SECRET, and SPOTIFY_REDIRECT_URI."
            )

        scope = (
            "user-modify-playback-state user-read-playback-state "
            "user-read-currently-playing user-top-read user-library-read "
            "user-read-recently-played"
        )
        oauth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            open_browser=True,
            cache_path=cache_path,
        )
        return spotipy.Spotify(auth_manager=oauth)


def _normalize_command(command: str) -> str | None:
    value = (command or "").strip().lower()
    aliases = {
        "play&pause": "play_pause",
        "play_pause": "play_pause",
        "toggle": "play_pause",
        "play": "play",
        "resume": "play",
        "pause": "pause",
        "next": "next",
        "skip": "next",
        "previous": "previous",
        "prev": "previous",
        "track_info": "track_info",
        "now_playing": "track_info",
        "volume": "volume",
        "set_volume": "volume",
        "play_random": "play_random",
        "random": "play_random",
    }
    return aliases.get(value)


def _parse_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except Exception:
        return None


def _clean_query(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _format_spotify_error(exc: SpotifyException) -> str:
    status = getattr(exc, "http_status", None)
    if status == 401:
        return "Spotify authorization failed. Re-authenticate the Spotify app."
    if status == 403:
        return "Spotify account/device does not allow this action."
    if status == 404:
        return "No active Spotify device found."
    if status == 429:
        return "Spotify rate limit reached. Try again shortly."
    reason = str(getattr(exc, "msg", "") or str(exc)).strip()
    return f"Spotify API error ({status or 'unknown'}): {reason}"


def _track_label(track: dict) -> str:
    name = str(track.get("name") or "Unknown track")
    artists = track.get("artists") or []
    artist_names = ", ".join(
        str(item.get("name") or "").strip()
        for item in artists
        if isinstance(item, dict)
    )
    if artist_names:
        return f"{name} by {artist_names}"
    return name


def _first_playable_track(items: list[dict]) -> dict | None:
    for item in items:
        if not isinstance(item, dict):
            continue
        uri = str(item.get("uri") or "").strip()
        if uri:
            return item
    return None


async def _play_pause(client: spotipy.Spotify) -> str:
    playback = await asyncio.to_thread(client.current_playback)
    is_playing = bool(playback and playback.get("is_playing"))
    if is_playing:
        await asyncio.to_thread(client.pause_playback)
        return "Playback paused."
    await asyncio.to_thread(client.start_playback)
    return "Playback resumed."


async def _play(client: spotipy.Spotify, *, query: str | None = None) -> str:
    if query:
        return await _play_from_query(client, query=query)
    return await _play_auto_pick(client)


async def _pause(client: spotipy.Spotify) -> str:
    await asyncio.to_thread(client.pause_playback)
    return "Playback paused."


async def _next_track(client: spotipy.Spotify) -> str:
    queue = await asyncio.to_thread(client.queue)
    await asyncio.to_thread(client.next_track)
    next_item = ((queue or {}).get("queue") or [None])[0]
    if isinstance(next_item, dict):
        return f"Skipped to next track: {_track_label(next_item)}."
    return "Skipped to next track."


async def _previous_track(client: spotipy.Spotify) -> str:
    await asyncio.to_thread(client.previous_track)
    return "Went to previous track."


async def _track_info(client: spotipy.Spotify) -> str:
    playback = await asyncio.to_thread(client.current_playback)
    if not playback:
        return "No active playback right now."

    item = playback.get("item")
    if not isinstance(item, dict):
        return "No track is currently playing."
    device_name = str((playback.get("device") or {}).get("name") or "").strip()
    label = _track_label(item)
    suffix = f" on {device_name}" if device_name else ""
    return f"Now playing: {label}{suffix}."


async def _set_volume(client: spotipy.Spotify, volume: int) -> str:
    target = max(0, min(100, int(volume)))
    await asyncio.to_thread(client.volume, target)
    return f"Volume set to {target}%."


async def _play_from_query(client: spotipy.Spotify, *, query: str) -> str:
    print(f"{SPOTIFY_TAG} play_from_query search_tracks query={query!r}")
    track_search = await asyncio.to_thread(
        client.search,
        q=query,
        type="track",
        limit=5,
    )
    track_items = list(((track_search or {}).get(
        "tracks") or {}).get("items") or [])
    selected_track = _first_playable_track(track_items)
    if selected_track is not None:
        print(f"{SPOTIFY_TAG} play_from_query hit=track")
        await asyncio.to_thread(client.start_playback, uris=[selected_track["uri"]])
        return f"Playing: {_track_label(selected_track)}."

    print(f"{SPOTIFY_TAG} play_from_query fallback=artist")
    artist_search = await asyncio.to_thread(
        client.search,
        q=query,
        type="artist",
        limit=3,
    )
    artist_items = list(((artist_search or {}).get(
        "artists") or {}).get("items") or [])
    first_artist = artist_items[0] if artist_items else None
    artist_id = str((first_artist or {}).get("id") or "").strip()
    if artist_id:
        top_payload = await asyncio.to_thread(client.artist_top_tracks, artist_id, country="US")
        top_tracks = list((top_payload or {}).get("tracks") or [])
        selected_artist_track = _first_playable_track(top_tracks)
        if selected_artist_track is not None:
            print(f"{SPOTIFY_TAG} play_from_query hit=artist_top_track")
            await asyncio.to_thread(client.start_playback, uris=[selected_artist_track["uri"]])
            artist_name = str((first_artist or {}).get("name") or "").strip()
            if artist_name:
                return f"Playing top track from {artist_name}: {_track_label(selected_artist_track)}."
            return f"Playing: {_track_label(selected_artist_track)}."

    print(f"{SPOTIFY_TAG} play_from_query fallback=auto_pick")
    fallback = await _play_auto_pick(client)
    if fallback.startswith("No Spotify tracks found"):
        return f"No Spotify match found for '{query}'."
    return f"No direct match for '{query}'. {fallback}"


async def _play_auto_pick(client: spotipy.Spotify) -> str:
    print(f"{SPOTIFY_TAG} auto_pick source=recent")
    recent_payload = await asyncio.to_thread(client.current_user_recently_played, limit=20)
    recent_items = list((recent_payload or {}).get("items") or [])
    recent_tracks = [
        item.get("track")
        for item in recent_items
        if isinstance(item, dict) and isinstance(item.get("track"), dict)
    ]
    recent_track = _first_playable_track(recent_tracks)

    if recent_track is not None:
        seed_id = str(recent_track.get("id") or "").strip()
        if seed_id:
            recommendations = await asyncio.to_thread(
                client.recommendations,
                seed_tracks=[seed_id],
                limit=20,
            )
            recommended_tracks = list(
                (recommendations or {}).get("tracks") or [])
            recommended_track = _first_playable_track(recommended_tracks)
            if recommended_track is not None:
                print(f"{SPOTIFY_TAG} auto_pick hit=recommendations")
                await asyncio.to_thread(client.start_playback, uris=[recommended_track["uri"]])
                return f"Playing something like your recent vibe: {_track_label(recommended_track)}."

        print(f"{SPOTIFY_TAG} auto_pick hit=recent_track")
        await asyncio.to_thread(client.start_playback, uris=[recent_track["uri"]])
        return f"Playing from your recent vibe: {_track_label(recent_track)}."

    print(f"{SPOTIFY_TAG} auto_pick source=top_tracks")
    top_payload = await asyncio.to_thread(
        client.current_user_top_tracks,
        20,
        0,
        "short_term",
    )
    top_tracks = list((top_payload or {}).get("items") or [])
    top_track = _first_playable_track(top_tracks)
    if top_track is not None:
        print(f"{SPOTIFY_TAG} auto_pick hit=top_track")
        await asyncio.to_thread(client.start_playback, uris=[top_track["uri"]])
        return f"Playing from your top tracks: {_track_label(top_track)}."

    print(f"{SPOTIFY_TAG} auto_pick source=saved_tracks")
    saved_payload = await asyncio.to_thread(client.current_user_saved_tracks, 20, 0)
    saved_tracks = [
        item.get("track")
        for item in (saved_payload or {}).get("items", [])
        if isinstance(item, dict) and isinstance(item.get("track"), dict)
    ]
    saved_track = _first_playable_track(saved_tracks)
    if saved_track is not None:
        print(f"{SPOTIFY_TAG} auto_pick hit=saved_track")
        await asyncio.to_thread(client.start_playback, uris=[saved_track["uri"]])
        return f"Playing from your saved tracks: {_track_label(saved_track)}."

    print(f"{SPOTIFY_TAG} auto_pick no_tracks_found")
    return "No Spotify tracks found in recent, top, or saved library."


async def _play_random(client: spotipy.Spotify) -> str:
    print(f"{SPOTIFY_TAG} play_random source=top_tracks")
    top_tracks = await asyncio.to_thread(
        client.current_user_top_tracks,
        50,
        0,
        "short_term",
    )
    items = list((top_tracks or {}).get("items") or [])

    if not items:
        print(f"{SPOTIFY_TAG} play_random fallback=saved_tracks")
        saved = await asyncio.to_thread(client.current_user_saved_tracks, 50, 0)
        items = [entry.get("track") for entry in (saved or {}).get(
            "items", []) if isinstance(entry, dict)]
        items = [track for track in items if isinstance(track, dict)]

    if not items:
        print(f"{SPOTIFY_TAG} play_random no_tracks_found")
        return "No Spotify tracks found in top or saved library."

    track = random.choice(items)
    uri = str(track.get("uri") or "").strip()
    if not uri:
        print(f"{SPOTIFY_TAG} play_random invalid_uri")
        return "Could not pick a playable Spotify track."

    await asyncio.to_thread(client.start_playback, uris=[uri])
    print(f"{SPOTIFY_TAG} play_random selected_track={_track_label(track)}")
    return f"Playing random track: {_track_label(track)}."
