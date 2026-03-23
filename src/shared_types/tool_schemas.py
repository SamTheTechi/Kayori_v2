from __future__ import annotations

from typing import Annotated, Any, Literal

from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class UserDeviceToolArgs(_InjectedStateArgs):
    command: Literal[
        "user_location",
        "toggle_flashlight",
        "find_phone",
    ] = Field(
        default="user_location",
        description="Device action command.",
    )


class SpotifyToolArgs(_InjectedStateArgs):
    command: Literal[
        "play",
        "play_track",
        "resume",
        "pause",
        "next",
        "previous",
        "now_playing",
        "volume_up",
        "volume_down",
    ] = Field(
        default="play",
        description="Spotify command.",
    )
    query: str | None = Field(
        default=None,
        min_length=1,
        description="Song or artist search text used with command='play_track'.",
    )
    step: int | None = Field(
        default=None,
        ge=1,
        le=25,
        description="Volume step used with volume_up and volume_down.",
    )

    @model_validator(mode="after")
    def validate_args(self) -> SpotifyToolArgs:
        if self.command == "play_track" and not self.query:
            raise ValueError("query is required when command='play_track'.")
        return self


__all__ = [
    "WeatherToolArgs",
    "ReminderToolArgs",
    "UserDeviceToolArgs",
    "SpotifyToolArgs",
]
