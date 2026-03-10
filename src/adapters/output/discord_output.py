from __future__ import annotations

from dataclasses import dataclass, replace

from adapters.runtime.discord_runtime import DiscordRuntime
from shared_types.models import MessageAttachment, MessageSource, OutboundMessage


@dataclass(slots=True)
class DiscordOutputAdapter:
    runtime: DiscordRuntime
    default_channel_id: str | None = None
    default_user_id: str | None = None

    name: str = "discord"
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
            print("[discord-output] dropped message with no discord route")
            return

        chunks = _split_discord_chunks(message.content, max_len=self.max_chunk_len)
        if not chunks:
            await self._send_one(message=message, route=route)
            return

        first = True
        for chunk in chunks:
            chunk_message = replace(
                message,
                content=chunk,
                reply_to_message_id=message.reply_to_message_id if first else None,
                mention_author=message.mention_author if first else False,
                attachments=message.attachments if first else [],
            )
            await self._send_one(message=chunk_message, route=route)
            first = False

    async def _send_one(
        self, *, message: OutboundMessage, route: tuple[str, str]
    ) -> None:
        mode, target_id = route
        content = _compose_text_with_media(message.content, message.attachments)
        if not (content or "").strip():
            return

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


def _compose_text_with_media(content: str, attachments: list[MessageAttachment]) -> str:
    if not attachments:
        return content
    lines = [content.strip()] if content.strip() else []
    lines.append("Media:")
    for item in attachments[:4]:
        detail = item.url or item.filename or "[embedded]"
        lines.append(f"- {item.kind}: {detail}")
    return "\n".join(lines)
