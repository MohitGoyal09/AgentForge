from __future__ import annotations

import abc
import asyncio
import random
from typing import Any, AsyncGenerator

from agentforge_harness.config.config import Config
from agentforge_harness.client.response import StreamEvent, StreamEventType


class BaseProvider(abc.ABC):
    """A single model provider behind one streaming interface.

    Subclasses implement ``_generate`` (the provider-specific request) and
    ``retryable_exceptions``. The shared ``chat_completion`` wraps generation in
    a capped exponential-backoff retry loop and converts a terminal failure into
    an ``ERROR`` stream event so the agent loop never sees a raw exception.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._max_retries: int = 3

    @abc.abstractmethod
    def _generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        stream: bool,
        model: str | None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Yield StreamEvents for a single attempt (no retry handling)."""
        raise NotImplementedError

    def retryable_exceptions(self) -> tuple[type[Exception], ...]:
        """Exception types that should trigger a retry. Override per provider."""
        return ()

    def _format_error(self, exc: Exception) -> str:
        return f"{type(exc).__name__}: {exc}"

    def _backoff_seconds(self, attempt: int) -> float:
        return 2 ** attempt + random.uniform(0, 1)

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = True,
        model: str | None = None,
        max_retries: int | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        retry_count = self._max_retries if max_retries is None else max_retries

        for attempt in range(retry_count + 1):
            emitted = False
            try:
                async for event in self._generate(
                    messages=messages,
                    tools=tools,
                    stream=stream,
                    model=model,
                ):
                    emitted = True
                    yield event
                return
            except self.retryable_exceptions() as exc:
                # Only retry when nothing was emitted yet this attempt, otherwise
                # a retry would replay partial output the caller already consumed.
                if attempt < retry_count and not emitted:
                    await asyncio.sleep(self._backoff_seconds(attempt))
                    continue
                yield StreamEvent(
                    type=StreamEventType.ERROR,
                    error=self._format_error(exc),
                )
                return

    async def close(self) -> None:
        """Release any underlying network clients. Override as needed."""
        return None
