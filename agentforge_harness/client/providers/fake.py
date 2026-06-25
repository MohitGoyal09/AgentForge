from __future__ import annotations

from typing import Any, AsyncGenerator, Callable

from agentforge_harness.config.config import Config
from agentforge_harness.client.providers.base import BaseProvider
from agentforge_harness.client.response import StreamEvent


class FakeProvider(BaseProvider):
    """Test provider that replays scripted StreamEvent sequences.

    Pass either a flat list of events (replayed on every call) or a callable that
    receives the call kwargs and returns the events for that call. Every call is
    recorded in ``calls`` for assertions.
    """

    def __init__(
        self,
        config: Config | None = None,
        events: list[StreamEvent] | Callable[[dict[str, Any]], list[StreamEvent]] | None = None,
    ) -> None:
        super().__init__(config or Config())
        self._events = events or []
        self.calls: list[dict[str, Any]] = []

    async def _generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        stream: bool,
        model: str | None,
    ) -> AsyncGenerator[StreamEvent, None]:
        call = {"messages": messages, "tools": tools, "stream": stream, "model": model}
        self.calls.append(call)

        events = self._events(call) if callable(self._events) else self._events
        for event in events:
            yield event
