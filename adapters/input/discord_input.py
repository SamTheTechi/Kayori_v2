from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import discord

from adapters.runtime.discord_runtime import DiscordMessageHandler, DiscordRuntime
from shared_types.models import MessageAttachment, MessageEnvelope
from shared_types.protocal import MessageBus


@dataclass(slots=True)
class DiscordInputAdapter:
    runtime: DiscordRuntime
    bus: MessageBus
    name: str = "discord-input"

    _stop_event: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)
    _handler: DiscordMessageHandler | None = field(default=None, init=False, repr=False)
    _acquired: bool = field(default=False, init=False, repr=False)

    async def start(self) -> None:
        self._stop_event.clear()
        self._handler = self._handle_message
        await self.runtime.register_message_handler(self._handler)
        await self.runtime.acquire()
        self._acquired = True

        try:
            await self._stop_event.wait()
        finally:
            await self._cleanup()

    async def stop(self) -> None:
        self._stop_event.set()
        await self._cleanup()

    async def _cleanup(self) -> None:
        handler = self._handler
        self._handler = None
        if handler is not None:
            await self.runtime.unregister_message_handler(handler)
        if self._acquired:
            self._acquired = False
            await self.runtime.release()

    async def _handle_message(self, message: discord.Message) -> None:
        content = (message.content or "").strip()
        attachments = _extract_attachments(message)
        if not content and not attachments:
            return

        envelope = MessageEnvelope(
            source="discord",
            content=content,
            is_dm=isinstance(message.channel, discord.DMChannel),
            message_id=str(message.id),
            channel_id=str(message.channel.id),
            author_id=str(message.author.id),
            attachments=attachments,
            metadata={
                "author_display_name": message.author.display_name,
                "attachment_count": len(attachments),
                "attachment_kinds": sorted({item.kind for item in attachments}),
            },
        )
        await self.bus.publish(envelope)


def _extract_attachments(message: discord.Message) -> list[MessageAttachment]:
    results: list[MessageAttachment] = []
    for attachment in message.attachments:
        mime_type = (attachment.content_type or "").lower()
        filename = (attachment.filename or "").lower()
        kind = _resolve_kind(mime_type=mime_type, filename=filename)

        results.append(
            MessageAttachment(
                kind=kind,
                url=str(attachment.url),
                mime_type=attachment.content_type,
                filename=attachment.filename,
                size_bytes=getattr(attachment, "size", None),
                width=getattr(attachment, "width", None),
                height=getattr(attachment, "height", None),
                duration_seconds=getattr(attachment, "duration", None),
            )
        )

    return results


def _resolve_kind(*, mime_type: str, filename: str) -> str:
    if mime_type.startswith("image/") or filename.endswith(
        (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".heic", ".heif")
    ):
        return "image"
    if mime_type.startswith("audio/") or filename.endswith((".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac")):
        return "audio"
    if mime_type.startswith("video/") or filename.endswith((".mp4", ".mov", ".mkv", ".webm", ".avi")):
        return "video"
    return "document"


DiscordGateway = DiscordInputAdapter
