from __future__ import annotations

from typing import Any, AsyncGenerator

import pytest

from agentforge_harness.client.providers.base import BaseProvider
from agentforge_harness.client.response import StreamEvent, StreamEventType
from agentforge_harness.config.config import Config, ModelConfig


class _RaisingProvider(BaseProvider):
    """A provider whose _generate raises a non-retryable ValueError."""

    def _generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        stream: bool,
        model: str | None,
    ) -> AsyncGenerator[StreamEvent, None]:
        raise ValueError("something went badly wrong")

    def retryable_exceptions(self) -> tuple[type[Exception], ...]:
        # ValueError is NOT in this tuple, so it is non-retryable.
        return (KeyError,)


@pytest.fixture
def provider(tmp_path):
    config = Config(cwd=tmp_path, model=ModelConfig(name="test/model"))
    return _RaisingProvider(config)


async def test_non_retryable_exception_becomes_error_event(provider):
    events: list[StreamEvent] = []
    raised = False
    try:
        async for event in provider.chat_completion(messages=[], tools=None):
            events.append(event)
    except Exception:
        raised = True

    assert not raised, "chat_completion must not propagate raw exceptions"
    assert len(events) == 1
    assert events[0].type == StreamEventType.ERROR
    assert "ValueError" in (events[0].error or "")
