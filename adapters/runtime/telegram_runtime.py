from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from telegram import Bot, Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters


TelegramUpdateHandler = Callable[[Update], Awaitable[None]]


@dataclass(slots=True)
class TelegramRuntime:
    token: str
    poll_timeout_seconds: int = 25
    poll_interval_seconds: float = 1.0
    name: str = "telegram-runtime"

    _application: Application = field(init=False, repr=False)
    _lock: asyncio.Lock = field(
        default_factory=asyncio.Lock, init=False, repr=False)
    _ref_count: int = field(default=0, init=False, repr=False)
    _poll_ref_count: int = field(default=0, init=False, repr=False)
    _started: bool = field(default=False, init=False, repr=False)
    _handlers: list[TelegramUpdateHandler] = field(
        default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        self._application = Application.builder().token(self.token).build()
        self._application.add_handler(
            MessageHandler(filters.ALL, self._on_update))

    async def register_message_handler(self, handler: TelegramUpdateHandler) -> None:
        async with self._lock:
            if handler not in self._handlers:
                self._handlers.append(handler)

    async def unregister_message_handler(self, handler: TelegramUpdateHandler) -> None:
        async with self._lock:
            self._handlers = [
                item for item in self._handlers if item is not handler]

    async def acquire(self) -> None:
        async with self._lock:
            self._ref_count += 1
            if self._ref_count == 1:
                await self._application.initialize()
                await self._application.start()
                self._started = True

    async def release(self) -> None:
        async with self._lock:
            if self._ref_count == 0:
                return

            self._ref_count -= 1
            if self._ref_count > 0:
                return

            if self._poll_ref_count > 0:
                updater = self._application.updater
                if updater is not None:
                    await updater.stop()
                self._poll_ref_count = 0

            if self._started:
                await self._application.stop()
                await self._application.shutdown()
                self._started = False

    async def acquire_polling(self) -> None:
        await self.acquire()

        async with self._lock:
            self._poll_ref_count += 1
            if self._poll_ref_count == 1:
                updater = self._application.updater
                if updater is None:
                    raise RuntimeError("Telegram updater is not available.")
                await updater.start_polling(
                    poll_interval=self.poll_interval_seconds,
                    timeout=self.poll_timeout_seconds,
                    allowed_updates=Update.ALL_TYPES,
                )
                print("[telegram] polling started")

    async def release_polling(self) -> None:
        should_release = False
        async with self._lock:
            if self._poll_ref_count > 0:
                self._poll_ref_count -= 1
                if self._poll_ref_count == 0:
                    updater = self._application.updater
                    if updater is not None:
                        await updater.stop()
            should_release = True

        if should_release:
            await self.release()

    @property
    def bot(self) -> Bot:
        return self._application.bot

    async def resolve_file_url(self, file_id: str) -> str | None:
        if not file_id:
            return None

        file_path: str | None = None
        telegram_file = await self._application.bot.get_file(file_id)
        file_path = telegram_file.file_path

        if not file_path:
            return None
        if file_path.startswith(("http://", "https://")):
            return file_path
        return f"https://api.telegram.org/file/bot{self.token}/{file_path}"

    async def _on_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        handlers = list(self._handlers)
        for handler in handlers:
            try:
                await handler(update)
            except Exception as exc:
                print(f"[telegram-runtime] handler error: {exc}")
