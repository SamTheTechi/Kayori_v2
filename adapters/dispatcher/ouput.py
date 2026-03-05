from __future__ import annotations

import asyncio
from dataclasses import dataclass

from shared_types.models import OutboundMessage
from shared_types.protocal import OutputAdapter


@dataclass(slots=True)
class MultiOutputDispatcher:
    outputs: list[OutputAdapter]
    name: str = "multi-output-dispatcher"

    async def start(self) -> None:
        for output in self.outputs:
            await output.start()

    async def stop(self) -> None:
        for output in reversed(self.outputs):
            await output.stop()

    async def send(self, message: OutboundMessage) -> None:
        if not self.outputs:
            return

        results = await asyncio.gather(
            *(output.send(message) for output in self.outputs),
            return_exceptions=True,
        )
        for output, result in zip(self.outputs, results):
            if isinstance(result, Exception):
                print(
                    f"[output-dispatcher] send failed on {output.name}: {result}")


__all__ = ["MultiOutputDispatcher"]
