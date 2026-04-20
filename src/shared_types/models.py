from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from langchain_core.messages import BaseMessage, messages_from_dict, messages_to_dict


EMOTIONS = (
    "Affection",
    "Amused",
    "Curious",
    "Concerned",
    "Disgusted",
    "Embarrassed",
    "Frustrated",

    "Trust",
    "Attachment",
    "Confidence",
)
FAST_EMOTIONS = (
    "Affection",
    "Amused",
    "Curious",
    "Concerned",
    "Disgusted",
    "Embarrassed",
    "Frustrated",
)
LONG_EMOTIONS = (
    "Trust",
    "Attachment",
    "Confidence",
)

MOOD_MIN = 0.0
MOOD_MAX = 1.0
MOOD_NEUTRAL = 0.5


class MessageSource(StrEnum):
    DISCORD = "discord"
    TELEGRAM = "telegram"
    CONSOLE = "console"
    WEBHOOK = "webhook"

    COMPACT = "compact"
    SCHEDULER = "scheduler"
    LIFE = "life"
    PROACTIVE = "proactive"


@dataclass(slots=True)
class MessagesHistory:
    _messages: list[BaseMessage] = field(default_factory=list)

    def append(self, msgs: list[BaseMessage]) -> None:
        self._messages.extend(msgs)

    def replace(self, msgs: list[BaseMessage]) -> None:
        """Used after compression — swap trimmed window back in."""
        self._messages = list(msgs)

    def all(self) -> list[BaseMessage]:
        return list(self._messages)

    def __len__(self) -> int:
        return len(self._messages)

    def as_dict(self) -> dict:
        return {"messages": messages_to_dict(self._messages)}

    @classmethod
    def from_dict(cls, data: dict) -> MessagesHistory:
        obj = cls()
        obj._messages = messages_from_dict(data.get("messages", []))
        return obj


@dataclass(slots=True)
class MoodState:
    Affection: float = MOOD_NEUTRAL
    Amused: float = MOOD_NEUTRAL
    Curious: float = MOOD_NEUTRAL
    Concerned: float = MOOD_NEUTRAL
    Disgusted: float = MOOD_NEUTRAL
    Embarrassed: float = MOOD_NEUTRAL
    Frustrated: float = MOOD_NEUTRAL
    Trust: float = MOOD_NEUTRAL
    Attachment: float = MOOD_NEUTRAL
    Confidence: float = MOOD_NEUTRAL

    def as_dict(self) -> dict[str, float]:
        return {
            "Affection": self.Affection,
            "Amused": self.Amused,
            "Curious": self.Curious,
            "Concerned": self.Concerned,
            "Disgusted": self.Disgusted,
            "Embarrassed": self.Embarrassed,
            "Frustrated": self.Frustrated,
            "Trust": self.Trust,
            "Attachment": self.Attachment,
            "Confidence": self.Confidence,
        }

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> MoodState:
        payload = {key: float(values.get(key, MOOD_NEUTRAL))
                   for key in EMOTIONS}
        return cls(**payload)

    def clamp(self) -> MoodState:
        for key in EMOTIONS:
            value = max(MOOD_MIN, min(MOOD_MAX, float(getattr(self, key))))
            setattr(self, key, round(value, 3))
        return self


@dataclass(slots=True)
class LifeNote:
    content: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat())
    kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": str(self.content or "").strip(),
            "timestamp": str(self.timestamp or "").strip(),
            "kind": str(self.kind or "").strip() or None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LifeNote":
        return cls(
            content=str(data.get("content", "")).strip(),
            timestamp=str(data.get("timestamp")
                          or datetime.now(UTC).isoformat()),
            kind=str(data.get("kind") or "").strip() or None,
        )

    @property
    def created_at(self) -> str:
        return self.timestamp


@dataclass(slots=True)
class InteractionState:
    last_user_message_at: str | None = None
    last_proactive_message_at: str | None = None
    ignored_proactive_count: int = 0
    proactive_sent_today: int = 0
    proactive_sent_day: str | None = None
    last_route_source: str | None = None
    last_channel_id: str | None = None
    last_target_user_id: str | None = None
    last_author_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "last_user_message_at": _maybe_str(self.last_user_message_at),
            "last_proactive_message_at": _maybe_str(self.last_proactive_message_at),
            "ignored_proactive_count": max(0, int(self.ignored_proactive_count or 0)),
            "proactive_sent_today": max(0, int(self.proactive_sent_today or 0)),
            "proactive_sent_day": _maybe_str(self.proactive_sent_day),
            "last_route_source": _maybe_str(self.last_route_source),
            "last_channel_id": _maybe_str(self.last_channel_id),
            "last_target_user_id": _maybe_str(self.last_target_user_id),
            "last_author_id": _maybe_str(self.last_author_id),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InteractionState":
        return cls(
            last_user_message_at=_maybe_str(data.get("last_user_message_at")),
            last_proactive_message_at=_maybe_str(
                data.get("last_proactive_message_at")),
            ignored_proactive_count=max(
                0, int(data.get("ignored_proactive_count", 0) or 0)),
            proactive_sent_today=max(
                0, int(data.get("proactive_sent_today", 0) or 0)),
            proactive_sent_day=_maybe_str(data.get("proactive_sent_day")),
            last_route_source=_maybe_str(data.get("last_route_source")),
            last_channel_id=_maybe_str(data.get("last_channel_id")),
            last_target_user_id=_maybe_str(data.get("last_target_user_id")),
            last_author_id=_maybe_str(data.get("last_author_id")),
        )


# @dataclass(slots=True)
# class LocationState:
#     latitude: float = 0.0
#     longitude: float = 0.0
#     timestamp: float = 0.0
#
#     def as_dict(self) -> dict[str, float]:
#         return {
#             "latitude": self.latitude,
#             "longitude": self.longitude,
#             "timestamp": self.timestamp,
#         }
#
#     @classmethod
#     def from_dict(cls, values: dict[str, Any]) -> LocationState:
#         return cls(
#             latitude=float(values.get("latitude", 0.0)),
#             longitude=float(values.get("longitude", 0.0)),
#             timestamp=float(values.get("timestamp", 0.0)),
#         )


# @dataclass(slots=True)
# class MessageAttachment:
#     kind: str = "image"
#     url: str = ""
#     mime_type: str | None = None
#     filename: str | None = None
#     size_bytes: int | None = None
#     width: int | None = None
#     height: int | None = None
#     duration_seconds: float | None = None
#     language: str | None = None
#     transcript: str | None = None
#     ocr_text: str | None = None
#     description: str | None = None
#
#     def to_dict(self) -> dict[str, Any]:
#         return {
#             "kind": self.kind,
#             "url": self.url,
#             "mime_type": self.mime_type,
#             "filename": self.filename,
#             "size_bytes": self.size_bytes,
#             "width": self.width,
#             "height": self.height,
#             "duration_seconds": self.duration_seconds,
#             "language": self.language,
#             "transcript": self.transcript,
#             "ocr_text": self.ocr_text,
#             "description": self.description,
#         }
#
#     @classmethod
#     def from_dict(cls, values: dict[str, Any]) -> MessageAttachment:
#         return cls(
#             kind=str(values.get("kind", "image")),
#             url=str(values.get("url", "")).strip(),
#             mime_type=_maybe_str(values.get("mime_type")),
#             filename=_maybe_str(values.get("filename")),
#             size_bytes=_maybe_int(values.get("size_bytes")),
#             width=_maybe_int(values.get("width")),
#             height=_maybe_int(values.get("height")),
#             duration_seconds=_maybe_float(values.get("duration_seconds")),
#             language=_maybe_str(values.get("language")),
#             transcript=_maybe_str(values.get("transcript")),
#             ocr_text=_maybe_str(values.get("ocr_text")),
#             description=_maybe_str(values.get("description")),
#         )


@dataclass(slots=True)
class AudioPayload:
    base64_data: str
    mime_type: str | None = None
    filename: str | None = None
    duration_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "base64_data": self.base64_data,
            "mime_type": self.mime_type,
            "filename": self.filename,
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AudioPayload | None":
        base64_data = _maybe_base64(data.get("base64_data"))
        if not base64_data:
            return None
        return cls(
            base64_data=base64_data,
            mime_type=_maybe_str(data.get("mime_type")),
            filename=_maybe_str(data.get("filename")),
            duration_seconds=_maybe_float(data.get("duration_seconds")),
        )

    @classmethod
    def from_legacy_dict(cls, data: dict[str, Any]) -> "AudioPayload | None":
        base64_data = _maybe_base64(data.get("audio_base64"))
        if not base64_data:
            return None
        return cls(
            base64_data=base64_data,
            mime_type=_maybe_str(data.get("audio_mime_type")),
            filename=_maybe_str(data.get("audio_filename")),
            duration_seconds=_maybe_float(data.get("audio_duration_seconds")),
        )

    @classmethod
    def from_bytes(
        cls,
        audio_bytes: bytes,
        *,
        mime_type: str | None = None,
        filename: str | None = None,
        duration_seconds: float | None = None,
    ) -> "AudioPayload":
        encoded = _encode_audio_base64(audio_bytes)
        if not encoded:
            raise ValueError("audio_bytes must be non-empty")
        return cls(
            base64_data=encoded,
            mime_type=_maybe_str(mime_type),
            filename=_maybe_str(filename),
            duration_seconds=duration_seconds,
        )

    def bytes(self) -> bytes | None:
        return _decode_audio_base64(self.base64_data)

@dataclass(slots=True)
class MessageEnvelope:
    source: MessageSource
    content: str | None = None
    channel_id: str | None = None
    author_id: str | None = None
    message_id: str | None = None
    target_user_id: str | None = None
    audio: AudioPayload | None = None
    voice_mode: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid4().hex)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.value,
            "content": self.content,
            "channel_id": self.channel_id,
            "author_id": self.author_id,
            "message_id": self.message_id,
            "target_user_id": self.target_user_id,
            "audio": self.audio.to_dict() if self.audio is not None else None,
            "voice_mode": self.voice_mode,
            "metadata": self.metadata,
            "id": self.id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MessageEnvelope:
        return cls(
            source=_message_source_from_any(data.get("source")),
            content=_maybe_str(data.get("content")),
            channel_id=_maybe_str(data.get("channel_id")),
            author_id=_maybe_str(data.get("author_id")),
            message_id=_maybe_str(data.get("message_id")),
            target_user_id=_maybe_str(data.get("target_user_id")),
            audio=_audio_payload_from_any(data),
            voice_mode=bool(data.get("voice_mode", False)),
            metadata=dict(data.get("metadata") or {}),
            id=str(data.get("id") or uuid4().hex),
        )

    def audio_bytes(self) -> bytes | None:
        if self.audio is None:
            return None
        return self.audio.bytes()

    @classmethod
    def from_audio_bytes(
        cls,
        *,
        source: MessageSource,
        audio_bytes: bytes,
        audio_mime_type: str | None = None,
        audio_filename: str | None = None,
        audio_duration_seconds: float | None = None,
        voice_mode: bool = True,
        content: str | None = None,
        channel_id: str | None = None,
        author_id: str | None = None,
        message_id: str | None = None,
        target_user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "MessageEnvelope":
        return cls(
            source=source,
            content=_maybe_str(content),
            channel_id=channel_id,
            author_id=author_id,
            message_id=message_id,
            target_user_id=target_user_id,
            audio=AudioPayload.from_bytes(
                audio_bytes,
                mime_type=audio_mime_type,
                filename=audio_filename,
                duration_seconds=audio_duration_seconds,
            ),
            voice_mode=bool(voice_mode),
            metadata=dict(metadata or {}),
        )


@dataclass(slots=True)
class OutboundMessage:
    source: MessageSource
    content: str | None = None
    channel_id: str | None = None
    target_user_id: str | None = None
    message_id: str | None = None
    audio: AudioPayload | None = None
    voice_mode: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    reply_to_message_id: str | None = None
    mention_author: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.value,
            "content": self.content,
            "channel_id": self.channel_id,
            "target_user_id": self.target_user_id,
            "message_id": self.message_id,
            "audio": self.audio.to_dict() if self.audio is not None else None,
            "voice_mode": self.voice_mode,
            "metadata": self.metadata,
            "reply_to_message_id": self.reply_to_message_id,
            "mention_author": self.mention_author,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OutboundMessage:
        return cls(
            source=_message_source_from_any(data.get("source")),
            content=_maybe_str(data.get("content")),
            channel_id=_maybe_str(data.get("channel_id")),
            target_user_id=_maybe_str(data.get("target_user_id")),
            message_id=_maybe_str(data.get("message_id")),
            audio=_audio_payload_from_any(data),
            voice_mode=bool(data.get("voice_mode", False)),
            metadata=dict(data.get("metadata") or {}),
            reply_to_message_id=_maybe_str(data.get("reply_to_message_id")),
            mention_author=bool(data.get("mention_author", False)),
        )

    def audio_bytes(self) -> bytes | None:
        if self.audio is None:
            return None
        return self.audio.bytes()

    @classmethod
    def from_audio_bytes(
        cls,
        *,
        source: MessageSource,
        audio_bytes: bytes,
        audio_mime_type: str | None = None,
        audio_filename: str | None = None,
        audio_duration_seconds: float | None = None,
        voice_mode: bool = True,
        content: str | None = None,
        channel_id: str | None = None,
        target_user_id: str | None = None,
        message_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        reply_to_message_id: str | None = None,
        mention_author: bool = False,
    ) -> "OutboundMessage":
        return cls(
            source=source,
            content=_maybe_str(content),
            channel_id=channel_id,
            target_user_id=target_user_id,
            message_id=message_id,
            audio=AudioPayload.from_bytes(
                audio_bytes,
                mime_type=audio_mime_type,
                filename=audio_filename,
                duration_seconds=audio_duration_seconds,
            ),
            voice_mode=bool(voice_mode),
            metadata=dict(metadata or {}),
            reply_to_message_id=reply_to_message_id,
            mention_author=mention_author,
        )


def _message_source_from_any(value: Any) -> MessageSource:
    if isinstance(value, MessageSource):
        return value
    try:
        return MessageSource(str(value or MessageSource.WEBHOOK.value).strip().lower())
    except Exception:
        return MessageSource.WEBHOOK


def _audio_payload_from_any(data: dict[str, Any]) -> AudioPayload | None:
    nested = data.get("audio")
    if isinstance(nested, dict):
        payload = AudioPayload.from_dict(nested)
        if payload is not None:
            return payload
    return AudioPayload.from_legacy_dict(data)


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


def _maybe_base64(value: Any) -> str | None:
    text = _maybe_str(value)
    if not text:
        return None
    try:
        base64.b64decode(text, validate=True)
    except Exception:
        return None
    return text


def _encode_audio_base64(audio_bytes: bytes | None) -> str | None:
    if not audio_bytes:
        return None
    return base64.b64encode(audio_bytes).decode("ascii")


def _decode_audio_base64(value: str | None) -> bytes | None:
    if not value:
        return None
    try:
        return base64.b64decode(value)
    except Exception:
        return None
