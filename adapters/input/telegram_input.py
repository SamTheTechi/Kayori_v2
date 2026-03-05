from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from telegram import Message, Update

from adapters.runtime.telegram_runtime import TelegramRuntime, TelegramUpdateHandler
from shared_types.models import MessageAttachment, MessageEnvelope
from shared_types.protocal import MessageBus


@dataclass(slots=True)
class TelegramInputAdapter:
    runtime: TelegramRuntime
    bus: MessageBus
    allowed_chat_ids: set[str] | None = None

    name: str = "telegram-input"
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)
    _handler: TelegramUpdateHandler | None = field(default=None, init=False, repr=False)
    _acquired: bool = field(default=False, init=False, repr=False)

    async def start(self) -> None:
        self._stop_event.clear()
        self._handler = self._handle_update
        await self.runtime.register_message_handler(self._handler)
        await self.runtime.acquire_polling()
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
            await self.runtime.release_polling()

    async def _handle_update(self, update: Update) -> None:
        message = update.effective_message
        if message is None:
            return

        chat = message.chat
        chat_id = str(chat.id)
        if self.allowed_chat_ids and chat_id not in self.allowed_chat_ids:
            return

        content = ((message.text or message.caption) or "").strip()
        attachments = await self._extract_media_attachments(message)
        if not content and not attachments:
            return

        user = message.from_user
        author_id = str(user.id) if user else None
        is_dm = str(chat.type).lower() == "private"

        envelope = MessageEnvelope(
            source="telegram",
            content=content,
            is_dm=is_dm,
            channel_id=chat_id,
            author_id=author_id,
            target_user_id=chat_id if is_dm else None,
            message_id=str(message.message_id) if message.message_id else None,
            attachments=attachments,
            metadata={
                "chat_type": str(chat.type),
                "chat_title": getattr(chat, "title", None),
                "author_username": user.username if user else None,
                "author_display_name": user.full_name if user else "",
                "attachment_count": len(attachments),
                "attachment_kinds": sorted({item.kind for item in attachments}),
            },
        )
        await self.bus.publish(envelope)

    async def _extract_media_attachments(self, message: Message) -> list[MessageAttachment]:
        attachments: list[MessageAttachment] = []

        if message.photo:
            best = message.photo[-1]
            file_url = await self.runtime.resolve_file_url(best.file_id)
            if file_url:
                attachments.append(
                    MessageAttachment(
                        kind="image",
                        url=file_url,
                        mime_type="image/jpeg",
                        filename=None,
                        size_bytes=best.file_size,
                        width=best.width,
                        height=best.height,
                    )
                )

        if message.document:
            document = message.document
            file_url = await self.runtime.resolve_file_url(document.file_id)
            if file_url:
                mime_type = str(document.mime_type or "").lower()
                attachments.append(
                    MessageAttachment(
                        kind=_kind_from_mime(mime_type, document.file_name),
                        url=file_url,
                        mime_type=document.mime_type,
                        filename=document.file_name,
                        size_bytes=document.file_size,
                        width=None,
                        height=None,
                    )
                )

        if message.voice:
            voice = message.voice
            file_url = await self.runtime.resolve_file_url(voice.file_id)
            if file_url:
                attachments.append(
                    MessageAttachment(
                        kind="voice",
                        url=file_url,
                        mime_type="audio/ogg",
                        filename=None,
                        size_bytes=voice.file_size,
                        duration_seconds=float(voice.duration),
                        language=voice.language_code,
                    )
                )

        if message.audio:
            audio = message.audio
            file_url = await self.runtime.resolve_file_url(audio.file_id)
            if file_url:
                attachments.append(
                    MessageAttachment(
                        kind="audio",
                        url=file_url,
                        mime_type=audio.mime_type,
                        filename=audio.file_name,
                        size_bytes=audio.file_size,
                        duration_seconds=float(audio.duration),
                    )
                )

        if message.video:
            video = message.video
            file_url = await self.runtime.resolve_file_url(video.file_id)
            if file_url:
                attachments.append(
                    MessageAttachment(
                        kind="video",
                        url=file_url,
                        mime_type=video.mime_type or "video/mp4",
                        filename=video.file_name,
                        size_bytes=video.file_size,
                        width=video.width,
                        height=video.height,
                        duration_seconds=float(video.duration),
                    )
                )

        if message.video_note:
            video_note = message.video_note
            file_url = await self.runtime.resolve_file_url(video_note.file_id)
            if file_url:
                attachments.append(
                    MessageAttachment(
                        kind="video",
                        url=file_url,
                        mime_type="video/mp4",
                        filename=None,
                        size_bytes=video_note.file_size,
                        width=video_note.length,
                        height=video_note.length,
                        duration_seconds=float(video_note.duration),
                    )
                )

        return attachments


def _kind_from_mime(mime_type: str, filename: str | None) -> str:
    filename_text = str(filename or "").lower()
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("audio/"):
        return "audio"
    if mime_type.startswith("video/"):
        return "video"
    if filename_text.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".heic", ".heif")):
        return "image"
    if filename_text.endswith((".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac")):
        return "audio"
    if filename_text.endswith((".mp4", ".mov", ".mkv", ".webm", ".avi")):
        return "video"
    return "document"


TelegramGateway = TelegramInputAdapter
