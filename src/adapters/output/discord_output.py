from __future__ import annotations

from dataclasses import dataclass, replace

from src.adapters.runtime.discord_runtime import DiscordRuntime
from src.logger import get_logger
from src.shared_types.models import MessageSource, OutboundMessage
from src.shared_types.protocol import OutputAdapter

logger = get_logger("output.discord")


@dataclass(slots=True)
class DiscordOutputAdapter(OutputAdapter):
    runtime: DiscordRuntime
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

        # if message.audio is not None:
        #     await self._send_audio(message=message, route=route)

        text = str(message.content or "").strip()

        chunk_message = replace(
            message,
            content=text,
            reply_to_message_id=message.reply_to_message_id,
            mention_author=message.mention_author,
        )
        await self._send_one(message=chunk_message, route=route)

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

    # async def _send_audio(
    #     self, *, message: OutboundMessage, route: tuple[str, str]
    # ) -> None:
    #     audio_bytes = message.audio_bytes()
    #     if not audio_bytes:
    #         return
    #
    #     payload = io.BytesIO(audio_bytes)
    #     payload.name = (
    #         message.audio.filename if message.audio else None) or "reply.audio"
    #     file = discord.File(payload, filename=payload.name)
    #     mode, target_id = route
    #     client = self.runtime.client
    #     if mode == "dm":
    #         user = await client.fetch_user(int(target_id))
    #         await user.send(file=file)
    #         return
    #
    #     channel = await client.fetch_channel(int(target_id))
    #     await channel.send(file=file)
    #


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
