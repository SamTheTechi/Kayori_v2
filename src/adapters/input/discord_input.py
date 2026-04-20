from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import discord

from src.adapters.runtime.discord_runtime import DiscordMessageHandler, DiscordRuntime
from src.adapters.runtime.discord_voice_runtime import (
    DiscordVoiceHandler,
    DiscordVoiceRuntime,
    DiscordVoiceUtterance,
)
from src.logger import get_logger
from src.shared_types.models import AudioPayload, MessageEnvelope, MessageSource
from src.shared_types.protocol import InputAdapter, MessageBus

logger = get_logger("input.discord_voice")


@dataclass(slots=True)
class DiscordInputAdapter(InputAdapter):
    runtime: DiscordRuntime
    bus: MessageBus
    name: str = "discord"

    _stop_event: asyncio.Event = field(
        default_factory=asyncio.Event, init=False, repr=False
    )
    _handler: DiscordMessageHandler | None = field(
        default=None, init=False, repr=False)
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

        envelope = MessageEnvelope(
            source=MessageSource.DISCORD,
            content=content,
            author_id=str(message.author.id),
            target_user_id=(
                str(message.author.id)
                if isinstance(message.channel, discord.DMChannel)
                else None
            ),
            channel_id=(
                None
                if isinstance(message.channel, discord.DMChannel)
                else str(message.channel.id)
            ),
            message_id=str(message.id),
            metadata={
                "author_display_name": message.author.display_name,
            },
        )
        await self.bus.publish(envelope)


@dataclass(slots=True)
class DiscordVoiceInputAdapter(InputAdapter):
    runtime: DiscordVoiceRuntime
    bus: MessageBus
    name: str = "discord-vc"

    _stop_event: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)
    _handler: DiscordVoiceHandler | None = field(default=None, init=False, repr=False)
    _acquired: bool = field(default=False, init=False, repr=False)

    async def start(self) -> None:
        self._stop_event.clear()
        self._handler = self._handle_utterance
        await self.runtime.register_handler(self._handler)
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
            await self.runtime.unregister_handler(handler)
        if self._acquired:
            self._acquired = False
            await self.runtime.release()

    async def _handle_utterance(self, utterance: DiscordVoiceUtterance) -> None:
        envelope = MessageEnvelope(
            source=MessageSource.DISCORD,
            content=None,
            channel_id=utterance.voice_channel_id,
            author_id=utterance.speaker_id,
            audio=AudioPayload.from_bytes(
                utterance.audio_bytes,
                mime_type=utterance.mime_type,
                filename=f"discord_vc_{utterance.speaker_id}.wav",
                duration_seconds=utterance.duration_seconds,
            ),
            voice_mode=True,
            metadata={
                "transport": "discord_vc",
                "guild_id": utterance.guild_id,
                "voice_channel_id": utterance.voice_channel_id,
                "speaker_id": utterance.speaker_id,
                "speaker_display_name": utterance.speaker_display_name,
                "session_kind": "voice_call",
            },
        )
        await logger.info(
            "discord_vc_envelope_published",
            "Published a Discord VC utterance to the bus.",
            context={
                "speaker_id": utterance.speaker_id,
                "voice_channel_id": utterance.voice_channel_id,
                "duration_seconds": utterance.duration_seconds,
            },
        )
        await self.bus.publish(envelope)
