from __future__ import annotations

import io
from dataclasses import dataclass, replace

from src.adapters.runtime.telegram_runtime import TelegramRuntime
from src.logger import get_logger
from src.shared_types.models import MessageSource, OutboundMessage
from src.shared_types.protocol import OutputAdapter

logger = get_logger("output.telegram")


@dataclass(slots=True)
class TelegramOutputAdapter(OutputAdapter):
    runtime: TelegramRuntime
    default_chat_id: str | None = None

    name: str = "telegram"
    route_source: MessageSource = MessageSource.TELEGRAM
    max_chunk_len: int = 4000
    _acquired: bool = False

    async def start(self) -> None:
        if self._acquired:
            return
        await self.runtime.acquire()
        self._acquired = True

    async def stop(self) -> None:
        if not self._acquired:
            return
        self._acquired = False
        await self.runtime.release()

    async def send(self, message: OutboundMessage) -> None:
        await self.start()

        chat_id = _resolve_chat_id(
            message=message, default_chat_id=self.default_chat_id
        )
        if not chat_id:
            await logger.warning(
                "telegram_output_dropped_no_route",
                "Dropped outbound Telegram message because no route was resolved.",
                context={
                    "source": str(message.source),
                    "channel_id": message.channel_id,
                    "target_user_id": message.target_user_id,
                },
            )
            return

        if message.audio is not None:
            await self._send_audio(chat_id=chat_id, message=message)

        text = str(message.content or "").strip()
        chunks = _split_telegram_chunks(text, max_len=self.max_chunk_len)
        if not chunks:
            return

        first = message.audio is None
        for chunk in chunks:
            chunk_message = replace(
                message,
                content=chunk,
                reply_to_message_id=message.reply_to_message_id if first else None,
            )
            await self._send_one(chat_id=chat_id, message=chunk_message)
            first = False

    async def _send_one(self, *, chat_id: str, message: OutboundMessage) -> None:
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "text": message.content
        }

        if message.source == MessageSource.TELEGRAM and message.reply_to_message_id:
            try:
                payload["reply_to_message_id"] = int(
                    message.reply_to_message_id)
            except Exception:
                pass

        await self.runtime.bot.send_message(**payload)

    async def _send_audio(self, *, chat_id: str, message: OutboundMessage) -> None:
        audio_bytes = message.audio_bytes()
        if not audio_bytes:
            return

        payload = io.BytesIO(audio_bytes)
        payload.name = (message.audio.filename if message.audio else None) or "reply.ogg"
        send_kwargs: dict[str, object] = {"chat_id": chat_id}

        if message.source == MessageSource.TELEGRAM and message.reply_to_message_id:
            try:
                send_kwargs["reply_to_message_id"] = int(message.reply_to_message_id)
            except Exception:
                pass

        mime_type = str((message.audio.mime_type if message.audio else None) or "").lower()
        if "ogg" in mime_type or message.voice_mode:
            await self.runtime.bot.send_voice(
                voice=payload,
                **send_kwargs,
            )
            return

        await self.runtime.bot.send_audio(
            audio=payload,
            **send_kwargs,
        )


def _resolve_chat_id(
    *, message: OutboundMessage, default_chat_id: str | None
) -> str | None:
    metadata = message.metadata or {}
    explicit = str(metadata.get("telegram_chat_id") or "").strip()
    if explicit:
        return explicit

    if message.target_user_id:
        return str(message.target_user_id)
    if message.channel_id:
        return str(message.channel_id)

    if default_chat_id:
        return str(default_chat_id)

    return None


def _split_telegram_chunks(content: str, max_len: int = 4000) -> list[str]:
    text = (content or "").strip()
    if not text:
        return []
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break

        split_at = remaining.rfind("\n", 0, max_len + 1)
        if split_at <= 0:
            split_at = max_len
        chunk = remaining[:split_at].rstrip()
        if not chunk:
            chunk = remaining[:max_len]
            split_at = len(chunk)
        chunks.append(chunk)
        remaining = remaining[split_at:].lstrip("\n")
    return chunks
