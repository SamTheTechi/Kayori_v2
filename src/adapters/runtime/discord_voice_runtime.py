from __future__ import annotations

import asyncio
import io
import os
import subprocess
import tempfile
import wave
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import discord

from src.adapters.runtime.discord_runtime import DiscordRuntime
from src.logger import get_logger

try:
    from discord.ext import voice_recv
    from discord.ext.voice_recv.opus import Decoder as VoiceRecvOpusDecoder
except Exception:  # pragma: no cover - optional runtime dependency
    voice_recv = None
    VoiceRecvOpusDecoder = None

try:
    from davey import MediaType as DaveMediaType
except Exception:  # pragma: no cover - optional runtime dependency
    DaveMediaType = None

logger = get_logger("runtime.discord_voice")


@dataclass(slots=True)
class DiscordVoiceUtterance:
    guild_id: str
    voice_channel_id: str
    speaker_id: str
    speaker_display_name: str
    audio_bytes: bytes
    mime_type: str = "audio/wav"
    duration_seconds: float | None = None


DiscordVoiceHandler = Callable[[DiscordVoiceUtterance], Awaitable[None]]


@dataclass(slots=True)
class _SpeakerBuffer:
    speaker_display_name: str
    pcm_bytes: bytearray = field(default_factory=bytearray)
    started_at: float = 0.0
    last_frame_at: float = 0.0
    frame_count: int = 0
    silent_packet_count: int = 0
    fake_packet_count: int = 0
    low_energy_frame_count: int = 0
    max_frame_average_abs: float = 0.0
    opus_decoder: Any | None = None
    watch_task: asyncio.Task[None] | None = None


@dataclass(slots=True)
class DiscordVoiceRuntime:
    runtime: DiscordRuntime
    voice_channel_id: str | None = None
    silence_seconds: float = 1.2
    min_utterance_seconds: float = 0.35
    max_utterance_seconds: float = 7.0
    sample_rate: int = 48000
    sample_width: int = 2
    channels: int = 2
    min_frame_average_abs: float = 8.0
    min_utterance_average_abs: float = 8.0
    name: str = "discord-voice-runtime"

    _handlers: list[DiscordVoiceHandler] = field(default_factory=list, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _ref_count: int = field(default=0, init=False, repr=False)
    _voice_client: Any | None = field(default=None, init=False, repr=False)
    _voice_loop: asyncio.AbstractEventLoop | None = field(default=None, init=False, repr=False)
    _speaker_buffers: dict[str, _SpeakerBuffer] = field(default_factory=dict, init=False, repr=False)
    _playback_active: bool = field(default=False, init=False, repr=False)
    _listen_error_streak: int = field(default=0, init=False, repr=False)
    _last_listen_error_at: float = field(default=0.0, init=False, repr=False)

    @property
    def enabled(self) -> bool:
        return bool(self.voice_channel_id)

    async def register_handler(self, handler: DiscordVoiceHandler) -> None:
        async with self._lock:
            if handler not in self._handlers:
                self._handlers.append(handler)

    async def unregister_handler(self, handler: DiscordVoiceHandler) -> None:
        async with self._lock:
            self._handlers = [item for item in self._handlers if item is not handler]

    async def acquire(self) -> None:
        if not self.enabled:
            raise RuntimeError("Discord VC is not configured.")
        if voice_recv is None:
            raise RuntimeError(
                "Discord VC requires a receive-capable extension such as discord-ext-voice-recv."
            )
        await self.runtime.acquire()
        async with self._lock:
            self._ref_count += 1
            if self._ref_count == 1:
                await self.runtime.register_voice_state_handler(
                    self._handle_voice_state_update
                )
                await logger.info(
                    "discord_vc_watch_started",
                    "Discord VC runtime is watching the target channel.",
                    context={"voice_channel_id": self.voice_channel_id},
                )
                await self._sync_connection_locked(reason="startup")

    async def release(self) -> None:
        should_release_runtime = False
        async with self._lock:
            if self._ref_count == 0:
                return
            self._ref_count -= 1
            if self._ref_count == 0:
                await self.runtime.unregister_voice_state_handler(
                    self._handle_voice_state_update
                )
                await self._disconnect_locked()
                should_release_runtime = True
        if should_release_runtime:
            await self.runtime.release()

    async def play_reply(
        self,
        *,
        audio_bytes: bytes,
        mime_type: str | None = None,
        voice_channel_id: str | None = None,
    ) -> bool:
        if not audio_bytes:
            return False
        await self.acquire()
        try:
            async with self._lock:
                voice_client = await self._connect_locked(
                    voice_channel_id=voice_channel_id,
                    require_members=False,
                    reason="playback",
                )
                if voice_client is None:
                    return False

            temp_path = await asyncio.to_thread(
                _write_temp_audio_file,
                audio_bytes,
                _audio_suffix(mime_type),
            )
            loop = asyncio.get_running_loop()
            finished = loop.create_future()
            self._playback_active = True
            await logger.info(
                "discord_vc_playback_started",
                "Discord VC playback started.",
                context={
                    "voice_channel_id": str(
                        getattr(getattr(voice_client, "channel", None), "id", "")
                    ),
                    "mime_type": mime_type,
                    "size_bytes": len(audio_bytes),
                },
            )

            def after_playback(error: Exception | None) -> None:
                def finalize() -> None:
                    self._playback_active = False
                    try:
                        os.unlink(temp_path)
                    except FileNotFoundError:
                        pass
                    if finished.done():
                        return
                    if error is not None:
                        finished.set_exception(error)
                    else:
                        finished.set_result(True)

                loop.call_soon_threadsafe(finalize)

            voice_client.play(
                discord.FFmpegPCMAudio(temp_path, stderr=subprocess.DEVNULL),
                after=after_playback,
            )
            await finished
            await logger.info(
                "discord_vc_playback_completed",
                "Discord VC playback completed.",
                context={
                    "voice_channel_id": str(
                        getattr(getattr(voice_client, "channel", None), "id", "")
                    )
                },
            )
            return True
        finally:
            await self.release()

    async def _sync_connection_locked(self, *, reason: str) -> None:
        voice_client = self._voice_client
        channel = await self._resolve_target_channel(
            voice_channel_id=self.voice_channel_id
        )
        if channel is None:
            return
        has_humans = _has_human_members(channel)
        if voice_client is not None and not has_humans:
            await logger.info(
                "discord_vc_empty_disconnect",
                "Discord VC disconnected because the channel is empty.",
                context={
                    "voice_channel_id": str(getattr(channel, "id", "")),
                    "reason": reason,
                },
            )
            await self._disconnect_locked()
            return
        if voice_client is None and has_humans:
            await self._connect_locked(reason=reason)
            return
        await logger.info(
            "discord_vc_sync_skipped",
            "Discord VC connection state did not change.",
            context={
                "voice_channel_id": str(getattr(channel, "id", "")),
                "reason": reason,
                "connected": voice_client is not None,
                "human_members": _human_member_count(channel),
            },
        )

    async def _connect_locked(
        self,
        *,
        voice_channel_id: str | None = None,
        require_members: bool = True,
        reason: str,
    ) -> Any | None:
        target_channel_id = str(voice_channel_id or self.voice_channel_id or "").strip()
        if not target_channel_id:
            raise RuntimeError("Discord VC requires DISCORD_VOICE_CHANNEL_ID.")

        channel = await self._resolve_target_channel(voice_channel_id=target_channel_id)
        if channel is None:
            return None
        if require_members and not _has_human_members(channel):
            await logger.info(
                "discord_vc_waiting_for_members",
                "Discord VC is waiting for a human member before joining.",
                context={
                    "voice_channel_id": str(getattr(channel, "id", "")),
                    "reason": reason,
                },
            )
            return None

        voice_client = self._voice_client
        if voice_client is not None and getattr(voice_client, "channel", None) is not None:
            if str(getattr(voice_client.channel, "id", "")) != target_channel_id:
                await voice_client.move_to(channel)
                await logger.info(
                    "discord_vc_moved",
                    "Discord VC moved to the target channel.",
                    context={
                        "voice_channel_id": target_channel_id,
                        "reason": reason,
                    },
                )
            return voice_client

        voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)
        self._start_listening(voice_client)
        self._voice_client = voice_client
        self._voice_loop = asyncio.get_running_loop()
        await logger.info(
            "discord_vc_connected",
            "Discord VC connected to the target channel.",
            context={
                "voice_channel_id": target_channel_id,
                "reason": reason,
                "human_members": _human_member_count(channel),
            },
        )
        return voice_client

    async def _disconnect_locked(self) -> None:
        self._clear_buffers()
        voice_client = self._voice_client
        self._voice_client = None
        self._voice_loop = None
        self._playback_active = False
        self._listen_error_streak = 0
        self._last_listen_error_at = 0.0
        if voice_client is None:
            return
        try:
            stop_listening = getattr(voice_client, "stop_listening", None)
            if callable(stop_listening):
                stop_listening()
        except Exception:
            pass
        await voice_client.disconnect(force=True)
        await logger.info(
            "discord_vc_disconnected",
            "Discord VC disconnected.",
            context={
                "voice_channel_id": str(
                    getattr(getattr(voice_client, "channel", None), "id", "")
                )
            },
        )

    async def _resolve_target_channel(self, *, voice_channel_id: str | None) -> Any | None:
        target_channel_id = str(voice_channel_id or "").strip()
        if not target_channel_id:
            return None
        client = self.runtime.client
        channel = client.get_channel(int(target_channel_id))
        if channel is None:
            channel = await client.fetch_channel(int(target_channel_id))
        return channel

    async def _handle_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if getattr(member, "bot", False):
            return
        target_channel_id = str(self.voice_channel_id or "").strip()
        if not target_channel_id:
            return
        before_channel_id = str(getattr(getattr(before, "channel", None), "id", ""))
        after_channel_id = str(getattr(getattr(after, "channel", None), "id", ""))
        if target_channel_id not in {before_channel_id, after_channel_id}:
            return
        await logger.info(
            "discord_vc_voice_state_changed",
            "Discord VC observed a relevant voice state update.",
            context={
                "member_id": str(member.id),
                "voice_channel_id": target_channel_id,
                "before_channel_id": before_channel_id,
                "after_channel_id": after_channel_id,
            },
        )
        async with self._lock:
            if self._ref_count == 0:
                return
            await self._sync_connection_locked(reason="voice_state_update")

    def push_frame(self, user: object, data: object) -> None:
        loop = self._voice_loop
        if loop is None:
            return
        loop.call_soon_threadsafe(self._handle_frame, user, data)

    def request_flush(self, speaker_id: str, *, reason: str) -> None:
        loop = self._voice_loop
        if loop is None:
            return
        loop.call_soon_threadsafe(
            lambda: asyncio.create_task(
                self._flush_speaker(speaker_id, reason=reason),
                name=f"discord-vc-flush-{speaker_id}-{reason}",
            )
        )

    def _start_listening(self, voice_client: Any) -> None:
        voice_client.listen(_DiscordVoiceSink(self), after=self._on_listen_after)

    def _on_listen_after(self, error: Exception | None) -> None:
        loop = self._voice_loop
        if loop is None:
            return

        def schedule() -> None:
            asyncio.create_task(
                self._handle_listen_after(error),
                name="discord-vc-listen-after",
            )

        loop.call_soon_threadsafe(schedule)

    async def _handle_listen_after(self, error: Exception | None) -> None:
        voice_client = self._voice_client
        is_listening = bool(
            getattr(voice_client, "is_listening", lambda: False)()
        ) if voice_client is not None else False
        await logger.info(
            "discord_vc_listen_stopped",
            "Discord VC listen loop stopped.",
            context={
                "voice_channel_id": str(
                    getattr(getattr(voice_client, "channel", None), "id", "")
                ),
                "had_error": error is not None,
                "is_listening": is_listening,
            },
        )
        delay_seconds = 0.0
        should_reconnect = False
        if error is not None:
            delay_seconds, should_reconnect = self._consume_listen_error(error)
            await logger.error(
                "discord_vc_listen_failed",
                "Discord VC listen loop failed.",
                context={
                    "voice_channel_id": str(
                        getattr(getattr(voice_client, "channel", None), "id", "")
                    ),
                    "restart_delay_seconds": round(delay_seconds, 3),
                    "listen_error_streak": self._listen_error_streak,
                    "reconnect_scheduled": should_reconnect,
                },
                error=error,
            )
        else:
            self._listen_error_streak = 0
            self._last_listen_error_at = 0.0
        if voice_client is None or self._ref_count <= 0:
            return
        is_connected = bool(getattr(voice_client, "is_connected", lambda: False)())
        if not is_connected or is_listening:
            return
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)
            voice_client = self._voice_client
            if voice_client is None or self._ref_count <= 0:
                return
            is_connected = bool(getattr(voice_client, "is_connected", lambda: False)())
            is_listening = bool(getattr(voice_client, "is_listening", lambda: False)())
            if not is_connected or is_listening:
                return
        if should_reconnect:
            async with self._lock:
                if voice_client is not self._voice_client or self._ref_count <= 0:
                    return
                channel_id = str(getattr(getattr(voice_client, "channel", None), "id", ""))
                await logger.info(
                    "discord_vc_listen_reconnect_scheduled",
                    "Discord VC is reconnecting after repeated listen failures.",
                    context={
                        "voice_channel_id": channel_id,
                        "listen_error_streak": self._listen_error_streak,
                    },
                )
                await self._disconnect_locked()
                await self._connect_locked(
                    voice_channel_id=channel_id or None,
                    require_members=False,
                    reason="listen_failure_reconnect",
                )
            return
        self._start_listening(voice_client)
        await logger.info(
            "discord_vc_listen_restarted",
            "Discord VC restarted the listen loop.",
            context={
                "voice_channel_id": str(
                    getattr(getattr(voice_client, "channel", None), "id", "")
                )
            },
        )
        self._listen_error_streak = 0
        self._last_listen_error_at = 0.0

    def _consume_listen_error(self, error: Exception) -> tuple[float, bool]:
        loop = self._voice_loop
        now = loop.time() if loop is not None else 0.0
        if self._last_listen_error_at and now - self._last_listen_error_at <= 2.0:
            self._listen_error_streak += 1
        else:
            self._listen_error_streak = 1
        self._last_listen_error_at = now

        if type(error).__name__ != "OpusError":
            return (0.25, self._listen_error_streak >= 4)

        if self._listen_error_streak >= 4:
            return (1.0, True)
        return (min(0.2 * self._listen_error_streak, 0.6), False)

    def _extract_pcm_bytes(
        self,
        *,
        user: object,
        data: object,
        buffer: _SpeakerBuffer,
    ) -> bytes:
        pcm = getattr(data, "pcm", None)
        if isinstance(pcm, (bytes, bytearray)) and pcm:
            return bytes(pcm)

        opus_packet = getattr(data, "opus", None)
        if not isinstance(opus_packet, (bytes, bytearray)) or not opus_packet:
            return b""

        decrypted_opus = self._decrypt_dave_audio_packet(
            user=user,
            opus_packet=bytes(opus_packet),
        )
        if not decrypted_opus:
            return b""

        decoder = buffer.opus_decoder
        if decoder is None:
            if VoiceRecvOpusDecoder is None:
                return b""
            decoder = VoiceRecvOpusDecoder()
            buffer.opus_decoder = decoder

        try:
            return bytes(decoder.decode(decrypted_opus, fec=False))
        except Exception as exc:
            asyncio.create_task(
                logger.error(
                    "discord_vc_opus_decode_failed",
                    "Discord VC failed to decode an inbound Opus packet.",
                    context={
                        "speaker_id": str(getattr(user, "id", "unknown") or "unknown"),
                        "voice_channel_id": str(
                            getattr(getattr(self._voice_client, "channel", None), "id", "")
                        ),
                        "opus_size_bytes": len(decrypted_opus),
                    },
                    error=exc,
                )
            )
            return b""

    def _decrypt_dave_audio_packet(
        self,
        *,
        user: object,
        opus_packet: bytes,
    ) -> bytes:
        voice_client = self._voice_client
        connection = getattr(voice_client, "_connection", None)
        dave_session = getattr(connection, "dave_session", None)
        dave_protocol_version = int(getattr(connection, "dave_protocol_version", 0) or 0)
        if dave_protocol_version <= 0 or dave_session is None or DaveMediaType is None:
            return opus_packet

        user_id_raw = getattr(user, "id", None)
        try:
            user_id = int(user_id_raw)
        except Exception:
            return b""

        try:
            return bytes(dave_session.decrypt(user_id, DaveMediaType.audio, opus_packet))
        except Exception as exc:
            asyncio.create_task(
                logger.error(
                    "discord_vc_dave_decrypt_failed",
                    "Discord VC failed to DAVE-decrypt an inbound audio packet.",
                    context={
                        "speaker_id": str(user_id),
                        "voice_channel_id": str(
                            getattr(getattr(self._voice_client, "channel", None), "id", "")
                        ),
                        "opus_size_bytes": len(opus_packet),
                        "dave_protocol_version": dave_protocol_version,
                    },
                    error=exc,
                )
            )
            return b""

    def _handle_frame(self, user: object, data: object) -> None:
        if self._playback_active:
            return
        if getattr(user, "bot", False):
            return
        client_user = getattr(self.runtime.client, "user", None)
        if client_user is not None and str(getattr(user, "id", "")) == str(getattr(client_user, "id", "")):
            return
        packet = getattr(data, "packet", None)
        packet_is_silence = bool(
            callable(getattr(packet, "is_silence", None)) and packet.is_silence()
        )
        packet_type = type(packet).__name__ if packet is not None else ""
        opus_bytes = getattr(data, "opus", None)
        opus_size_bytes = len(opus_bytes) if isinstance(opus_bytes, (bytes, bytearray)) else 0
        raw_pcm = getattr(data, "pcm", None)
        preview_pcm_bytes = bytes(raw_pcm) if isinstance(raw_pcm, (bytes, bytearray)) else b""
        preview_frame_average_abs = _pcm_average_abs(
            preview_pcm_bytes,
            sample_width=self.sample_width,
        ) if preview_pcm_bytes else 0.0

        speaker_id = str(getattr(user, "id", "unknown") or "unknown")
        speaker_name = (
            str(getattr(user, "display_name", "")).strip()
            or str(getattr(user, "name", "")).strip()
            or speaker_id
        )
        buffer = self._speaker_buffers.get(speaker_id)
        if buffer is None:
            loop = self._voice_loop
            if loop is None:
                return
            buffer = _SpeakerBuffer(
                speaker_display_name=speaker_name,
                started_at=loop.time(),
                last_frame_at=loop.time(),
            )
            self._speaker_buffers[speaker_id] = buffer
            asyncio.create_task(
                logger.info(
                    "discord_vc_first_frame",
                    "Discord VC received the first PCM frame for a speaker.",
                    context={
                        "speaker_id": speaker_id,
                        "voice_channel_id": str(
                            getattr(getattr(self._voice_client, "channel", None), "id", "")
                        ),
                        "packet_type": packet_type,
                        "packet_is_silence": packet_is_silence,
                        "opus_size_bytes": opus_size_bytes,
                        "pcm_size_bytes": len(preview_pcm_bytes),
                        "frame_average_abs": round(preview_frame_average_abs, 3),
                    },
                )
            )
            buffer.watch_task = asyncio.create_task(
                self._watch_speaker(speaker_id),
                name=f"discord-vc-watch-{speaker_id}",
            )
        if packet_is_silence:
            buffer.silent_packet_count += 1
        if packet_type == "FakePacket":
            buffer.fake_packet_count += 1
        pcm_bytes = self._extract_pcm_bytes(user=user, data=data, buffer=buffer)
        if not pcm_bytes:
            buffer.low_energy_frame_count += 1
            return
        frame_average_abs = _pcm_average_abs(
            pcm_bytes,
            sample_width=self.sample_width,
        )
        if frame_average_abs < self.min_frame_average_abs:
            buffer.low_energy_frame_count += 1
        buffer.max_frame_average_abs = max(buffer.max_frame_average_abs, frame_average_abs)
        buffer.pcm_bytes.extend(pcm_bytes)
        buffer.frame_count += 1
        if self._voice_loop is None:
            return
        now = self._voice_loop.time()
        buffer.last_frame_at = now
        elapsed = now - buffer.started_at
        if elapsed >= self.max_utterance_seconds:
            asyncio.create_task(
                logger.info(
                    "discord_vc_forced_flush_scheduled",
                    "Discord VC reached max utterance duration and is forcing a flush.",
                    context={
                        "speaker_id": speaker_id,
                        "voice_channel_id": str(
                            getattr(getattr(self._voice_client, "channel", None), "id", "")
                        ),
                        "elapsed_seconds": round(elapsed, 3),
                    },
                )
            )
            asyncio.create_task(
                self._flush_speaker(speaker_id, reason="max_duration"),
                name=f"discord-vc-force-flush-{speaker_id}",
            )

    async def _flush_speaker(self, speaker_id: str, *, reason: str) -> None:
        buffer = self._speaker_buffers.pop(speaker_id, None)
        voice_client = self._voice_client
        if buffer is None or not buffer.pcm_bytes or voice_client is None:
            return
        watch_task = buffer.watch_task
        buffer.watch_task = None
        current_task = asyncio.current_task()
        if watch_task is not None and watch_task is not current_task:
            watch_task.cancel()
            await asyncio.gather(watch_task, return_exceptions=True)
        duration_seconds = _pcm_duration_seconds(
            len(buffer.pcm_bytes),
            sample_rate=self.sample_rate,
            sample_width=self.sample_width,
            channels=self.channels,
        )
        average_abs = _pcm_average_abs(
            bytes(buffer.pcm_bytes),
            sample_width=self.sample_width,
        )
        if duration_seconds < self.min_utterance_seconds:
            await logger.info(
                "discord_vc_utterance_dropped_short",
                "Discord VC dropped a too-short utterance before STT.",
                context={
                    "speaker_id": speaker_id,
                    "voice_channel_id": str(getattr(voice_client.channel, "id", "")),
                    "duration_seconds": duration_seconds,
                    "min_utterance_seconds": self.min_utterance_seconds,
                    "reason": reason,
                    "frame_count": buffer.frame_count,
                    "low_energy_frame_count": buffer.low_energy_frame_count,
                    "silent_packet_count": buffer.silent_packet_count,
                    "fake_packet_count": buffer.fake_packet_count,
                    "max_frame_average_abs": round(buffer.max_frame_average_abs, 3),
                },
            )
            return
        if average_abs < self.min_utterance_average_abs:
            await logger.info(
                "discord_vc_utterance_dropped_silent",
                "Discord VC dropped a near-silent utterance before STT.",
                context={
                    "speaker_id": speaker_id,
                    "voice_channel_id": str(getattr(voice_client.channel, "id", "")),
                    "duration_seconds": duration_seconds,
                    "average_abs": round(average_abs, 3),
                    "min_utterance_average_abs": self.min_utterance_average_abs,
                    "reason": reason,
                    "frame_count": buffer.frame_count,
                    "low_energy_frame_count": buffer.low_energy_frame_count,
                    "silent_packet_count": buffer.silent_packet_count,
                    "fake_packet_count": buffer.fake_packet_count,
                    "max_frame_average_abs": round(buffer.max_frame_average_abs, 3),
                },
            )
            return
        utterance = DiscordVoiceUtterance(
            guild_id=str(getattr(voice_client.guild, "id", "")),
            voice_channel_id=str(getattr(voice_client.channel, "id", "")),
            speaker_id=speaker_id,
            speaker_display_name=buffer.speaker_display_name,
            audio_bytes=_pcm_to_wav_bytes(
                bytes(buffer.pcm_bytes),
                sample_rate=self.sample_rate,
                sample_width=self.sample_width,
                channels=self.channels,
            ),
            duration_seconds=duration_seconds,
        )
        await logger.info(
            "discord_vc_utterance_flushed",
            "Discord VC captured an utterance.",
            context={
                "speaker_id": speaker_id,
                "voice_channel_id": utterance.voice_channel_id,
                "duration_seconds": utterance.duration_seconds,
                "size_bytes": len(utterance.audio_bytes),
                "reason": reason,
                "frame_count": buffer.frame_count,
                "low_energy_frame_count": buffer.low_energy_frame_count,
                "silent_packet_count": buffer.silent_packet_count,
                "fake_packet_count": buffer.fake_packet_count,
                "max_frame_average_abs": round(buffer.max_frame_average_abs, 3),
            },
        )
        for handler in list(self._handlers):
            asyncio.create_task(
                self._dispatch(handler, utterance),
                name=f"discord-vc-dispatch-{speaker_id}",
            )

    async def _dispatch(
        self,
        handler: DiscordVoiceHandler,
        utterance: DiscordVoiceUtterance,
    ) -> None:
        try:
            await handler(utterance)
        except Exception as exc:
            await logger.error(
                "discord_vc_handler_failed",
                "Discord VC handler failed.",
                context={
                    "speaker_id": utterance.speaker_id,
                    "voice_channel_id": utterance.voice_channel_id,
                },
                error=exc,
            )

    def _clear_buffers(self) -> None:
        for buffer in self._speaker_buffers.values():
            if buffer.watch_task is not None:
                buffer.watch_task.cancel()
        self._speaker_buffers.clear()

    async def _watch_speaker(self, speaker_id: str) -> None:
        try:
            await logger.info(
                "discord_vc_watcher_started",
                "Discord VC started a per-speaker watcher.",
                context={
                    "speaker_id": speaker_id,
                    "voice_channel_id": str(
                        getattr(getattr(self._voice_client, "channel", None), "id", "")
                    ),
                },
            )
            while True:
                await asyncio.sleep(0.2)
                if self._playback_active:
                    continue
                loop = self._voice_loop
                buffer = self._speaker_buffers.get(speaker_id)
                if loop is None or buffer is None:
                    return
                voice_client = self._voice_client
                speaking = None
                if voice_client is not None:
                    guild = getattr(voice_client, "guild", None)
                    member = None
                    if guild is not None:
                        member = guild.get_member(int(speaker_id))
                    get_speaking = getattr(voice_client, "get_speaking", None)
                    if member is not None and callable(get_speaking):
                        try:
                            speaking = get_speaking(member)
                        except Exception:
                            speaking = None
                now = loop.time()
                active_for = now - buffer.started_at
                inactive_for = now - buffer.last_frame_at
                if active_for >= self.max_utterance_seconds:
                    await logger.info(
                        "discord_vc_forced_flush_scheduled",
                        "Discord VC reached max utterance duration and is forcing a flush.",
                        context={
                            "speaker_id": speaker_id,
                            "voice_channel_id": str(
                                getattr(getattr(self._voice_client, "channel", None), "id", "")
                            ),
                            "elapsed_seconds": round(active_for, 3),
                            "frame_count": buffer.frame_count,
                        },
                    )
                    await self._flush_speaker(speaker_id, reason="max_duration")
                    return
                if speaking is False and inactive_for >= 0.1:
                    await logger.info(
                        "discord_vc_speaking_state_flush",
                        "Discord VC is flushing because Discord reports the speaker stopped speaking.",
                        context={
                            "speaker_id": speaker_id,
                            "voice_channel_id": str(
                                getattr(getattr(self._voice_client, "channel", None), "id", "")
                            ),
                            "inactive_seconds": round(inactive_for, 3),
                            "frame_count": buffer.frame_count,
                        },
                    )
                    await self._flush_speaker(speaker_id, reason="speaking_state")
                    return
                if inactive_for < self.silence_seconds:
                    continue
                await logger.info(
                    "discord_vc_inactive_flush",
                    "Discord VC is flushing an inactive speaker buffer.",
                    context={
                        "speaker_id": speaker_id,
                        "voice_channel_id": str(
                            getattr(getattr(self._voice_client, "channel", None), "id", "")
                        ),
                        "inactive_seconds": round(inactive_for, 3),
                        "frame_count": buffer.frame_count,
                    },
                )
                await self._flush_speaker(speaker_id, reason="inactivity")
                return
        except asyncio.CancelledError:
            return
        except Exception as exc:
            await logger.error(
                "discord_vc_watcher_failed",
                "Discord VC speaker watcher failed.",
                context={
                    "speaker_id": speaker_id,
                    "voice_channel_id": str(
                        getattr(getattr(self._voice_client, "channel", None), "id", "")
                    ),
                },
                error=exc,
            )


class _DiscordVoiceSink(voice_recv.AudioSink if voice_recv is not None else object):  # type: ignore[misc]
    def __init__(self, runtime: DiscordVoiceRuntime) -> None:
        if voice_recv is not None:
            super().__init__()
        self.runtime = runtime

    def wants_opus(self) -> bool:
        return True

    def write(self, user: object, data: object) -> None:
        self.runtime.push_frame(user, data)

    @voice_recv.AudioSink.listener() if voice_recv is not None else (lambda f: f)
    def on_voice_member_speaking_stop(self, member: discord.Member) -> None:
        self.runtime.request_flush(
            str(member.id),
            reason="speaking_stop",
        )

    @voice_recv.AudioSink.listener() if voice_recv is not None else (lambda f: f)
    def on_voice_member_disconnect(
        self,
        member: discord.Member,
        ssrc: int | None,
    ) -> None:
        del ssrc
        self.runtime.request_flush(
            str(member.id),
            reason="member_disconnect",
        )

    def cleanup(self) -> None:
        self.runtime._clear_buffers()


def _pcm_to_wav_bytes(
    pcm_bytes: bytes,
    *,
    sample_rate: int,
    sample_width: int,
    channels: int,
) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buffer.getvalue()


def _pcm_duration_seconds(
    pcm_size_bytes: int,
    *,
    sample_rate: int,
    sample_width: int,
    channels: int,
) -> float:
    bytes_per_second = max(1, sample_rate * sample_width * channels)
    return round(float(pcm_size_bytes) / float(bytes_per_second), 3)


def _pcm_average_abs(
    pcm_bytes: bytes,
    *,
    sample_width: int,
) -> float:
    if not pcm_bytes or sample_width != 2:
        return 0.0
    sample_count = len(pcm_bytes) // sample_width
    if sample_count <= 0:
        return 0.0
    total = 0
    for index in range(0, sample_count * sample_width, sample_width):
        value = int.from_bytes(
            pcm_bytes[index:index + sample_width],
            byteorder="little",
            signed=True,
        )
        total += abs(value)
    return float(total) / float(sample_count)


def _audio_suffix(mime_type: str | None) -> str:
    mime = str(mime_type or "").strip().lower()
    if "wav" in mime:
        return ".wav"
    if "ogg" in mime:
        return ".ogg"
    if "mpeg" in mime or "mp3" in mime:
        return ".mp3"
    return ".audio"


def _write_temp_audio_file(audio_bytes: bytes, suffix: str) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(audio_bytes)
        return handle.name


def _human_member_count(channel: Any) -> int:
    members = getattr(channel, "members", None) or []
    return sum(1 for member in members if not getattr(member, "bot", False))


def _has_human_members(channel: Any) -> bool:
    return _human_member_count(channel) > 0
