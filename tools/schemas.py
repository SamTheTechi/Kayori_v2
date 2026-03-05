from __future__ import annotations

from typing import Any, Literal
from typing_extensions import Annotated

from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, ConfigDict, Field


class _InjectedStateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Annotated[dict[str, Any], InjectedState]


class WeatherToolArgs(_InjectedStateArgs):
    unit: Literal["c", "f"] = Field(
        default="c",
        description="Temperature unit preference for responses.",
    )
    location_override: str | None = Field(
        default=None,
        description="Optional location string override, e.g. 'Bengaluru'.",
    )


class ReminderToolArgs(_InjectedStateArgs):
    delay_minutes: int = Field(
        default=15,
        ge=1,
        le=24 * 60,
        description="Reminder delay in minutes.",
    )
    content: str | None = Field(
        default=None,
        min_length=1,
        description="Reminder text. If omitted, uses the latest user message.",
    )
    target_user_id: str | None = Field(
        default=None,
        description="Optional explicit user id/chat id for delivery.",
    )


class UserDeviceToolArgs(_InjectedStateArgs):
    command: Literal[
        "user_location",
        "toggle_flashlight",
        "find_phone",
        "speak_to_user",
    ] = Field(
        default="user_location",
        description="Device action command.",
    )
    content: str | None = Field(
        default=None,
        description="Speech content for speak_to_user command.",
    )


class SpotifyToolArgs(_InjectedStateArgs):
    command: Literal[
        "play_pause",
        "play",
        "resume",
        "pause",
        "next",
        "skip",
        "previous",
        "track_info",
        "now_playing",
        "volume",
        "set_volume",
        "play_random",
        "random",
    ] = Field(
        default="play_random",
        description="Spotify command.",
    )
    volume: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Target volume 0-100. Required for volume/set_volume commands.",
    )
    query: str | None = Field(
        default=None,
        min_length=1,
        description="Song/artist search text used with command='play'.",
    )
