from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from shared_types.models import MessageEnvelope
from shared_types.protocal import MessageBus


@dataclass(slots=True)
class ConsoleInputGateway:
    bus: MessageBus
    prompt: str = "You: "
    channel_id: str = "console"
    author_id: str = "local-user"
    exit_commands: set[str] = field(default_factory=lambda: {"exit", "quit"})

    name: str = "console"
    _stop_event: asyncio.Event = field(
        default_factory=asyncio.Event, init=False, repr=False)

    async def start(self) -> None:
        self._stop_event.clear()
        print("[console] input ready (type 'exit' to stop)")

        while not self._stop_event.is_set():
            try:
                line = await asyncio.to_thread(input, self.prompt)
            except EOFError:
                self._stop_event.set()
                break
            except KeyboardInterrupt:
                self._stop_event.set()
                break

            text = (line or "").strip()
            if not text:
                continue

            if text.lower() in self.exit_commands:
                self._stop_event.set()
                break

            envelope = MessageEnvelope(
                source="console",
                content=text,
                is_dm=True,
                channel_id=self.channel_id,
                author_id=self.author_id,
                target_user_id=self.channel_id,
                metadata={"transport": "stdin"},
            )
            await self.bus.publish(envelope)

    async def stop(self) -> None:
        self._stop_event.set()
