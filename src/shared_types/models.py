from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

EMOTIONS = (
    "Affection",
    "Amused",
    "Confidence",
    "Frustrated",
    "Concerned",
    "Curious",
    "Trust",
    "Calmness",
)
SLOW_EMOTIONS = ("Trust", "Confidence", "Calmness")
FAST_EMOTIONS = ("Affection", "Amused", "Frustrated", "Concerned", "Curious")
MOOD_MIN = 0.0
MOOD_MAX = 1.0
MOOD_NEUTRAL = 0.5


class MessageSource(StrEnum):
    DISCORD = "discord"
    TELEGRAM = "telegram"
    CONSOLE = "console"
    WEBHOOK = "webhook"
    REMINDER = "reminder"
    INTERNAL = "internal"


@dataclass(slots=True)
class MoodState:
    Affection: float = MOOD_NEUTRAL
    Amused: float = MOOD_NEUTRAL
    Confidence: float = MOOD_NEUTRAL
    Frustrated: float = MOOD_NEUTRAL
    Concerned: float = MOOD_NEUTRAL
    Curious: float = MOOD_NEUTRAL
    Trust: float = MOOD_NEUTRAL
    Calmness: float = MOOD_NEUTRAL

    def as_dict(self) -> dict[str, float]:
        return {
            "Affection": self.Affection,
            "Amused": self.Amused,
            "Confidence": self.Confidence,
            "Frustrated": self.Frustrated,
            "Concerned": self.Concerned,
            "Curious": self.Curious,
            "Trust": self.Trust,
            "Calmness": self.Calmness,
        }

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> MoodState:
        payload = {key: float(values.get(key, MOOD_NEUTRAL)) for key in EMOTIONS}
        return cls(**payload)

    def clamp(self) -> MoodState:
        for key in EMOTIONS:
            value = max(MOOD_MIN, min(MOOD_MAX, float(getattr(self, key))))
            setattr(self, key, round(value, 3))
        return self


@dataclass(slots=True)
class LocationState:
    latitude: float = 0.0
    longitude: float = 0.0
    timestamp: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> LocationState:
        return cls(
            latitude=float(values.get("latitude", 0.0)),
            longitude=float(values.get("longitude", 0.0)),
            timestamp=float(values.get("timestamp", 0.0)),
        )


@dataclass(slots=True)
class MessageAttachment:
    kind: str = "image"
    url: str = ""
    mime_type: str | None = None
    filename: str | None = None
    size_bytes: int | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    language: str | None = None
    transcript: str | None = None
    ocr_text: str | None = None
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "url": self.url,
            "mime_type": self.mime_type,
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "width": self.width,
            "height": self.height,
            "duration_seconds": self.duration_seconds,
            "language": self.language,
            "transcript": self.transcript,
            "ocr_text": self.ocr_text,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> MessageAttachment:
        return cls(
            kind=str(values.get("kind", "image")),
            url=str(values.get("url", "")).strip(),
            mime_type=_maybe_str(values.get("mime_type")),
            filename=_maybe_str(values.get("filename")),
            size_bytes=_maybe_int(values.get("size_bytes")),
            width=_maybe_int(values.get("width")),
            height=_maybe_int(values.get("height")),
            duration_seconds=_maybe_float(values.get("duration_seconds")),
            language=_maybe_str(values.get("language")),
            transcript=_maybe_str(values.get("transcript")),
            ocr_text=_maybe_str(values.get("ocr_text")),
            description=_maybe_str(values.get("description")),
        )


@dataclass(slots=True)
class MessageEnvelope:
    source: MessageSource
    content: str
    channel_id: str | None = None
    author_id: str | None = None
    message_id: str | None = None
    target_user_id: str | None = None
    attachments: list[MessageAttachment] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def thread_id(self, fallback_user_id: str | None = None) -> str:
        if self.channel_id:
            return str(self.channel_id)
        if self.target_user_id:
            return str(self.target_user_id)
        if self.author_id:
            return str(self.author_id)
        if fallback_user_id:
            return str(fallback_user_id)
        return "global"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.value,
            "content": self.content,
            "channel_id": self.channel_id,
            "author_id": self.author_id,
            "target_user_id": self.target_user_id,
            "attachments": [attachment.to_dict() for attachment in self.attachments],
            "metadata": self.metadata,
            "id": self.id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MessageEnvelope:
        return cls(
            source=_message_source_from_any(data.get("source")),
            content=str(data.get("content", "")).strip(),
            channel_id=_maybe_str(data.get("channel_id")),
            author_id=_maybe_str(data.get("author_id")),
            target_user_id=_maybe_str(data.get("target_user_id")),
            attachments=_attachments_from_any(data.get("attachments")),
            metadata=dict(data.get("metadata") or {}),
            id=str(data.get("id") or uuid4().hex),
            created_at=str(data.get("created_at") or datetime.now(UTC).isoformat()),
        )


@dataclass(slots=True)
class OutboundMessage:
    source: MessageSource
    content: str
    channel_id: str | None = None
    target_user_id: str | None = None
    message_id: str | None = None
    attachments: list[MessageAttachment] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    reply_to_message_id: str | None = None
    mention_author: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.value,
            "content": self.content,
            "channel_id": self.channel_id,
            "target_user_id": self.target_user_id,
            "message_id": self.message_id,
            "attachments": [attachment.to_dict() for attachment in self.attachments],
            "metadata": self.metadata,
            "created_at": self.created_at,
            "reply_to_message_id": self.reply_to_message_id,
            "mention_author": self.mention_author,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OutboundMessage:
        return cls(
            source=_message_source_from_any(data.get("source")),
            content=str(data.get("content", "")).strip(),
            channel_id=_maybe_str(data.get("channel_id")),
            target_user_id=_maybe_str(data.get("target_user_id")),
            message_id=_maybe_str(data.get("message_id")),
            attachments=_attachments_from_any(data.get("attachments")),
            metadata=dict(data.get("metadata") or {}),
            created_at=str(data.get("created_at") or datetime.now(UTC).isoformat()),
            reply_to_message_id=_maybe_str(data.get("reply_to_message_id")),
            mention_author=bool(data.get("mention_author", False)),
        )


def _message_source_from_any(value: Any) -> MessageSource:
    if isinstance(value, MessageSource):
        return value
    try:
        return MessageSource(str(value or MessageSource.INTERNAL.value).strip().lower())
    except Exception:
        return MessageSource.INTERNAL


def _maybe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _attachments_from_any(value: Any) -> list[MessageAttachment]:
    if not value:
        return []
    if isinstance(value, list):
        attachments: list[MessageAttachment] = []
        for item in value:
            if isinstance(item, MessageAttachment):
                attachments.append(item)
            elif isinstance(item, dict):
                parsed = MessageAttachment.from_dict(item)
                if parsed.url:
                    attachments.append(parsed)
        return attachments
    return []
