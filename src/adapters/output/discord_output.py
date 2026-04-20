from __future__ import annotations

import io
from dataclasses import dataclass, replace

import discord

from src.adapters.runtime.discord_runtime import DiscordRuntime
from src.adapters.runtime.discord_voice_runtime import DiscordVoiceRuntime
from src.logger import get_logger
from src.shared_types.models import MessageSource, OutboundMessage
from src.shared_types.protocol import OutputAdapter

logger = get_logger("output.discord")


@dataclass(slots=True)
class DiscordOutputAdapter(OutputAdapter):
    runtime: DiscordRuntime
    voice_runtime: DiscordVoiceRuntime | None = None
    default_channel_id: str | None = None
    default_user_id: str | None = None

    name: str = "discord"
    route_source: MessageSource = MessageSource.DISCORD
    max_chunk_len: int = 1900
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

        if _is_voice_route(message):
            played = await self._send_voice_reply(message)
            if played or message.voice_mode:
                return

        route = _resolve_route(
            message=message,
            default_channel_id=self.default_channel_id,
            default_user_id=self.default_user_id,
        )
        if route is None:
            await logger.warning(
                "discord_output_dropped_no_route",
                "Dropped outbound Discord message because no route was resolved.",
                context={
                    "source": str(message.source),
                    "channel_id": message.channel_id,
                    "target_user_id": message.target_user_id,
                },
            )
            return

        if message.audio is not None:
            await self._send_audio(message=message, route=route)

        text = str(message.content or "").strip()
        chunks = _split_discord_chunks(text, max_len=self.max_chunk_len)
        if not chunks:
            return

        first = message.audio is None
        for chunk in chunks:
            chunk_message = replace(
                message,
                content=chunk,
                reply_to_message_id=message.reply_to_message_id if first else None,
                mention_author=message.mention_author if first else False,
            )
            await self._send_one(message=chunk_message, route=route)
            first = False

    async def _send_one(
        self, *, message: OutboundMessage, route: tuple[str, str]
    ) -> None:
        content = message.content.strip()
        if not (content or "").strip():
            return

        mode, target_id = route
        client = self.runtime.client

        if mode == "dm":
            user = await client.fetch_user(int(target_id))
            await user.send(content)
            return

        channel = await client.fetch_channel(int(target_id))

        should_reply = message.source == MessageSource.DISCORD and bool(
            message.reply_to_message_id
        )
        if should_reply:
            try:
                original = await channel.fetch_message(int(message.reply_to_message_id))
                reaction = str(message.metadata.get("reaction", "")).strip()
                if reaction:
                    try:
                        await original.add_reaction(reaction)
                    except Exception:
                        pass
                await original.reply(content, mention_author=message.mention_author)
                return
            except Exception:
                pass

        await channel.send(content)

    async def _send_audio(
        self, *, message: OutboundMessage, route: tuple[str, str]
    ) -> None:
        audio_bytes = message.audio_bytes()
        if not audio_bytes:
            return

        payload = io.BytesIO(audio_bytes)
        payload.name = (
            message.audio.filename if message.audio else None) or "reply.audio"
        file = discord.File(payload, filename=payload.name)
        mode, target_id = route
        client = self.runtime.client
        if mode == "dm":
            user = await client.fetch_user(int(target_id))
            await user.send(file=file)
            return

        channel = await client.fetch_channel(int(target_id))
        await channel.send(file=file)

    async def _send_voice_reply(self, message: OutboundMessage) -> bool:
        voice_runtime = self.voice_runtime
        if voice_runtime is None:
            return False
        audio_bytes = message.audio_bytes()
        if not audio_bytes:
            return False
        voice_channel_id = str(
            message.metadata.get("voice_channel_id")
            or message.metadata.get("discord_voice_channel_id")
            or message.channel_id
            or voice_runtime.voice_channel_id
            or ""
        ).strip() or None
        await logger.info(
            "discord_vc_reply_routed",
            "Routing outbound Discord VC reply to voice playback.",
            context={
                "voice_channel_id": voice_channel_id,
                "mime_type": message.audio.mime_type if message.audio else None,
                "size_bytes": len(audio_bytes),
            },
        )
        return await voice_runtime.play_reply(
            audio_bytes=audio_bytes,
            mime_type=message.audio.mime_type if message.audio else None,
            voice_channel_id=voice_channel_id,
        )


def _resolve_route(
    *,
    message: OutboundMessage,
    default_channel_id: str | None,
    default_user_id: str | None,
) -> tuple[str, str] | None:
    metadata = message.metadata or {}
    explicit_channel = str(metadata.get("discord_channel_id") or "").strip()
    if explicit_channel:
        return ("channel", explicit_channel)

    explicit_user = str(metadata.get("discord_user_id") or "").strip()
    if explicit_user:
        return ("dm", explicit_user)

    if message.target_user_id:
        return ("dm", str(message.target_user_id))
    if message.channel_id:
        return ("channel", str(message.channel_id))

    if default_channel_id:
        return ("channel", str(default_channel_id))
    if default_user_id:
        return ("dm", str(default_user_id))

    return None


def _split_discord_chunks(content: str, max_len: int = 1900) -> list[str]:
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


def _is_voice_route(message: OutboundMessage) -> bool:
    metadata = message.metadata or {}
    transport = str(metadata.get("transport") or "").strip().lower()
    session_kind = str(metadata.get("session_kind") or "").strip().lower()
    return transport == "discord_vc" or session_kind == "voice_call"
