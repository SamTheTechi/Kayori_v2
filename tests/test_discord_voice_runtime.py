from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.adapters.runtime.discord_voice_runtime import DiscordVoiceRuntime


class _DummyRuntime:
    client = SimpleNamespace(user=None)


class _VoiceClient:
    def __init__(self) -> None:
        self.channel = SimpleNamespace(id="123")
        self.guild = SimpleNamespace(id="456")
        self._listening = False
        self._connected = True

    def is_listening(self) -> bool:
        return self._listening

    def is_connected(self) -> bool:
        return self._connected


class OpusError(Exception):
    pass


@pytest.mark.asyncio
async def test_consume_listen_error_backs_off_for_clustered_opus_errors() -> None:
    runtime = DiscordVoiceRuntime(runtime=_DummyRuntime(), voice_channel_id="123")
    runtime._voice_loop = asyncio.get_running_loop()

    first_delay, first_reconnect = runtime._consume_listen_error(OpusError("corrupted stream"))
    second_delay, second_reconnect = runtime._consume_listen_error(OpusError("corrupted stream"))
    third_delay, third_reconnect = runtime._consume_listen_error(OpusError("corrupted stream"))
    fourth_delay, fourth_reconnect = runtime._consume_listen_error(OpusError("corrupted stream"))

    assert (first_delay, first_reconnect) == (0.2, False)
    assert (second_delay, second_reconnect) == (0.4, False)
    assert (third_delay, third_reconnect) == (0.6, False)
    assert (fourth_delay, fourth_reconnect) == (1.0, True)


@pytest.mark.asyncio
async def test_handle_listen_after_restarts_without_reconnect_for_single_opus_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = DiscordVoiceRuntime(runtime=_DummyRuntime(), voice_channel_id="123")
    runtime._voice_loop = asyncio.get_running_loop()
    runtime._voice_client = _VoiceClient()
    runtime._ref_count = 1

    sleep_calls: list[float] = []
    restarted: list[str] = []

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    def fake_start_listening(self: DiscordVoiceRuntime, voice_client: object) -> None:
        restarted.append(str(getattr(getattr(voice_client, "channel", None), "id", "")))

    async def fail_disconnect(self: DiscordVoiceRuntime) -> None:
        raise AssertionError("disconnect should not be called for a single OpusError")

    monkeypatch.setattr("src.adapters.runtime.discord_voice_runtime.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(DiscordVoiceRuntime, "_start_listening", fake_start_listening)
    monkeypatch.setattr(DiscordVoiceRuntime, "_disconnect_locked", fail_disconnect)

    await runtime._handle_listen_after(OpusError("corrupted stream"))

    assert sleep_calls == [0.2]
    assert restarted == ["123"]


@pytest.mark.asyncio
async def test_handle_frame_ignores_silent_pcm() -> None:
    runtime = DiscordVoiceRuntime(runtime=_DummyRuntime(), voice_channel_id="123")
    runtime._voice_loop = asyncio.get_running_loop()
    runtime._voice_client = _VoiceClient()

    user = SimpleNamespace(id="speaker", display_name="speaker", name="speaker", bot=False)
    data = SimpleNamespace(pcm=b"\x00" * 3840)

    runtime._handle_frame(user, data)

    buffer = runtime._speaker_buffers["speaker"]
    assert buffer.frame_count == 1
    assert buffer.low_energy_frame_count == 1
    assert len(buffer.pcm_bytes) == 3840


@pytest.mark.asyncio
async def test_flush_speaker_drops_too_short_utterance() -> None:
    runtime = DiscordVoiceRuntime(
        runtime=_DummyRuntime(),
        voice_channel_id="123",
        min_utterance_seconds=0.35,
        min_utterance_average_abs=1.0,
    )
    runtime._voice_client = _VoiceClient()
    runtime._speaker_buffers["speaker"] = SimpleNamespace(
        speaker_display_name="speaker",
        pcm_bytes=bytearray((100).to_bytes(2, "little", signed=True) * 1000),
        frame_count=3,
        silent_packet_count=0,
        fake_packet_count=0,
        low_energy_frame_count=0,
        max_frame_average_abs=100.0,
        watch_task=None,
    )

    dispatched: list[object] = []

    async def handler(utterance: object) -> None:
        dispatched.append(utterance)

    runtime._handlers.append(handler)

    await runtime._flush_speaker("speaker", reason="speaking_stop")

    assert dispatched == []


@pytest.mark.asyncio
async def test_handle_frame_counts_discord_silence_packets() -> None:
    runtime = DiscordVoiceRuntime(runtime=_DummyRuntime(), voice_channel_id="123")
    runtime._voice_loop = asyncio.get_running_loop()
    runtime._voice_client = _VoiceClient()

    class _SilentPacket:
        def is_silence(self) -> bool:
            return True

    user = SimpleNamespace(id="speaker", display_name="speaker", name="speaker", bot=False)
    data = SimpleNamespace(pcm=b"\x00" * 3840, packet=_SilentPacket())

    runtime._handle_frame(user, data)

    buffer = runtime._speaker_buffers["speaker"]
    assert buffer.silent_packet_count == 1
    assert buffer.low_energy_frame_count == 1
    assert buffer.frame_count == 1
