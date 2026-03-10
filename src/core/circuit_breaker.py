from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, TypeVar

T = TypeVar("T")


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open and not allowing requests."""

    def __init__(
        self,
        name: str,
        retry_after_seconds: float | None = None,
    ) -> None:
        self.name = name
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"Circuit '{name}' is open. Retry after {retry_after_seconds}s."
            if retry_after_seconds
            else ""
        )


@dataclass(slots=True)
class CircuitBreaker:
    """
    Circuit breaker for external service calls.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Service failing, fail fast without calling external API
    - HALF_OPEN: Testing if service recovered (allow 1 request)
    """

    name: str
    failure_threshold: int = 5
    success_threshold: int = 2
    recovery_timeout_seconds: float = 30.0
    half_open_max_calls: int = 1

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False, repr=False)
    _failure_count: int = field(default=0, init=False, repr=False)
    _success_count: int = field(default=0, init=False, repr=False)
    _last_failure_time: float | None = field(default=None, init=False, repr=False)
    _last_state_change: float = field(default_factory=time.time, init=False, repr=False)
    _half_open_calls: int = field(default=0, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def is_closed(self) -> bool:
        return self._state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        return self._state == CircuitState.HALF_OPEN

    async def call(
        self,
        func: Callable[[], Any],
        *,
        fallback: Any = None,
    ) -> Any:
        """
        Execute function through circuit breaker.

        Args:
            func: Async function to execute
            fallback: Optional fallback value if circuit is open

        Returns:
            Result from func or fallback

        Raises:
            CircuitOpenError: If circuit is open and no fallback provided
        """
        async with self._lock:
            if not self._allow_request():
                if fallback is not None:
                    return fallback
                retry_after = self._retry_after_seconds()
                raise CircuitOpenError(self.name, retry_after_seconds=retry_after)

            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func()
            else:
                result = func()
            await self._on_success()
            return result
        except Exception:
            await self._on_failure()
            if fallback is not None:
                return fallback
            raise

    async def _allow_request(self) -> bool:
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.HALF_OPEN:
            return self._half_open_calls < self.half_open_max_calls

        if self._state == CircuitState.OPEN:
            if self._retry_after_seconds() <= 0:
                self._transition_to(CircuitState.HALF_OPEN)
                return True
            return False

        return False

    def _retry_after_seconds(self) -> float:
        if self._last_failure_time is None:
            return 0.0
        elapsed = time.time() - self._last_failure_time
        return max(0.0, self.recovery_timeout_seconds - elapsed)

    async def _on_success(self) -> None:
        async with self._lock:
            self._success_count += 1
            self._failure_count = 0

            if self._state == CircuitState.HALF_OPEN:
                if self._success_count >= self.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
            elif self._state == CircuitState.CLOSED:
                pass

    async def _on_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            self._success_count = 0
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)
            elif (
                self._state == CircuitState.CLOSED
                and self._failure_count >= self.failure_threshold
            ):
                self._transition_to(CircuitState.OPEN)

    def _transition_to(self, new_state: CircuitState) -> None:
        if self._state == new_state:
            return
        old_state = self._state
        self._state = new_state
        self._last_state_change = time.time()

        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._success_count = 0

        print(
            f"[circuit:{self.name}] state change: {old_state.value} → {new_state.value}"
        )

    def reset(self) -> None:
        """Manually reset circuit to closed state."""
        self._transition_to(CircuitState.CLOSED)
        self._last_failure_time = None

    def get_stats(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "last_failure_time": self._last_failure_time,
            "last_state_change": self._last_state_change,
            "half_open_calls": self._half_open_calls,
        }


__all__ = ["CircuitBreaker", "CircuitOpenError", "CircuitState"]
