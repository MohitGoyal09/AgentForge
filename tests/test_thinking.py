from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from agentforge_harness.client.providers import AnthropicProvider, OpenAICompatibleProvider
from agentforge_harness.client.response import StreamEvent, StreamEventType
from agentforge_harness.client.thinking import (
    ThinkingLevel,
    anthropic_thinking_budget,
    is_enabled,
    openai_reasoning_effort,
)
from agentforge_harness.config.config import Config, ModelConfig, ModelProvider


# --------------------------------------------------------------------------- #
# thinking.py mappings
# --------------------------------------------------------------------------- #


def test_anthropic_thinking_budget_off_returns_none():
    assert anthropic_thinking_budget(ThinkingLevel.OFF) is None


def test_anthropic_thinking_budget_high_returns_int():
    budget = anthropic_thinking_budget(ThinkingLevel.HIGH)
    assert isinstance(budget, int)
    assert budget > 0


def test_anthropic_thinking_budget_each_level():
    # OFF → None, all others → positive int
    assert anthropic_thinking_budget(ThinkingLevel.OFF) is None
    for level in (
        ThinkingLevel.MINIMAL,
        ThinkingLevel.LOW,
        ThinkingLevel.MEDIUM,
        ThinkingLevel.HIGH,
        ThinkingLevel.XHIGH,
    ):
        budget = anthropic_thinking_budget(level)
        assert isinstance(budget, int) and budget > 0


def test_openai_reasoning_effort_off_returns_none():
    assert openai_reasoning_effort(ThinkingLevel.OFF) is None


def test_openai_reasoning_effort_high_returns_high():
    assert openai_reasoning_effort(ThinkingLevel.HIGH) == "high"


def test_openai_reasoning_effort_xhigh_returns_high():
    # Providers cap at "high"
    assert openai_reasoning_effort(ThinkingLevel.XHIGH) == "high"


def test_openai_reasoning_effort_medium_returns_medium():
    assert openai_reasoning_effort(ThinkingLevel.MEDIUM) == "medium"


def test_is_enabled_off_is_false():
    assert is_enabled(ThinkingLevel.OFF) is False


def test_is_enabled_non_off_levels_are_true():
    for level in (
        ThinkingLevel.MINIMAL,
        ThinkingLevel.LOW,
        ThinkingLevel.MEDIUM,
        ThinkingLevel.HIGH,
        ThinkingLevel.XHIGH,
    ):
        assert is_enabled(level) is True


# --------------------------------------------------------------------------- #
# AnthropicProvider._build_kwargs — thinking enabled
# --------------------------------------------------------------------------- #


def test_anthropic_build_kwargs_thinking_high_injects_thinking_block(tmp_path: Path):
    config = Config(
        cwd=tmp_path,
        model=ModelConfig(
            provider=ModelProvider.ANTHROPIC,
            name="claude",
            thinking=ThinkingLevel.HIGH,
        ),
    )
    provider = AnthropicProvider(config)
    kwargs = provider._build_kwargs(
        messages=[{"role": "user", "content": "hello"}],
        tools=None,
        model=None,
    )

    budget = anthropic_thinking_budget(ThinkingLevel.HIGH)
    assert kwargs["thinking"] == {"type": "enabled", "budget_tokens": budget}
    assert kwargs["temperature"] == 1.0
    assert kwargs["max_tokens"] > budget


def test_anthropic_build_kwargs_thinking_off_omits_thinking_key(tmp_path: Path):
    config = Config(
        cwd=tmp_path,
        model=ModelConfig(
            provider=ModelProvider.ANTHROPIC,
            name="claude",
            thinking=ThinkingLevel.OFF,
        ),
    )
    provider = AnthropicProvider(config)
    kwargs = provider._build_kwargs(
        messages=[{"role": "user", "content": "hello"}],
        tools=None,
        model=None,
    )

    assert "thinking" not in kwargs
    # Temperature should be the configured value (default 1 in ModelConfig, but not forced to 1.0 by thinking)
    assert kwargs["temperature"] == config.temperature


# --------------------------------------------------------------------------- #
# OpenAICompatibleProvider — reasoning_effort kwarg
# --------------------------------------------------------------------------- #


async def test_openai_provider_sends_reasoning_effort_when_medium(monkeypatch):
    captured: dict = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="ok", tool_calls=None),
                        finish_reason="stop",
                    )
                ],
                usage=SimpleNamespace(
                    prompt_tokens=1,
                    completion_tokens=1,
                    total_tokens=2,
                    prompt_tokens_details=None,
                ),
            )

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    config = Config(
        cwd=Path("/tmp"),
        model=ModelConfig(
            provider=ModelProvider.OPENAI,
            name="gpt-4o",
            thinking=ThinkingLevel.MEDIUM,
        ),
    )
    provider = OpenAICompatibleProvider(config)
    monkeypatch.setattr(provider, "get_client", lambda: FakeClient())

    _ = [
        event
        async for event in provider.chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            stream=False,
        )
    ]

    assert captured.get("reasoning_effort") == "medium"


async def test_openai_provider_omits_reasoning_effort_when_off(monkeypatch):
    captured: dict = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="ok", tool_calls=None),
                        finish_reason="stop",
                    )
                ],
                usage=SimpleNamespace(
                    prompt_tokens=1,
                    completion_tokens=1,
                    total_tokens=2,
                    prompt_tokens_details=None,
                ),
            )

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    config = Config(
        cwd=Path("/tmp"),
        model=ModelConfig(
            provider=ModelProvider.OPENAI,
            name="gpt-4o",
            thinking=ThinkingLevel.OFF,
        ),
    )
    provider = OpenAICompatibleProvider(config)
    monkeypatch.setattr(provider, "get_client", lambda: FakeClient())

    _ = [
        event
        async for event in provider.chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            stream=False,
        )
    ]

    assert "reasoning_effort" not in captured


# --------------------------------------------------------------------------- #
# AnthropicProvider streaming — thinking_delta event
# --------------------------------------------------------------------------- #


class _FakeAnthropicStream:
    def __init__(self, events):
        self._events = list(events)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._events:
            raise StopAsyncIteration
        return self._events.pop(0)


class _FakeStreamManager:
    def __init__(self, events):
        self._events = events

    async def __aenter__(self):
        return _FakeAnthropicStream(self._events)

    async def __aexit__(self, *exc):
        return False


def _stream_script_with_thinking():
    return [
        SimpleNamespace(
            type="message_start",
            message=SimpleNamespace(usage=SimpleNamespace(input_tokens=10)),
        ),
        # thinking_delta event
        SimpleNamespace(
            type="content_block_delta",
            index=0,
            delta=SimpleNamespace(type="thinking_delta", thinking="reasoning..."),
        ),
        # regular text_delta after thinking
        SimpleNamespace(
            type="content_block_delta",
            index=1,
            delta=SimpleNamespace(type="text_delta", text="Answer."),
        ),
        SimpleNamespace(
            type="message_delta",
            delta=SimpleNamespace(stop_reason="end_turn"),
            usage=SimpleNamespace(output_tokens=5),
        ),
    ]


async def test_anthropic_streaming_emits_thinking_delta(monkeypatch):
    class FakeMessages:
        def stream(self, **kwargs):
            return _FakeStreamManager(_stream_script_with_thinking())

    class FakeAnthropicClient:
        messages = FakeMessages()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    config = Config(
        cwd=Path("/tmp"),
        model=ModelConfig(
            provider=ModelProvider.ANTHROPIC,
            name="claude",
            thinking=ThinkingLevel.HIGH,
        ),
    )
    provider = AnthropicProvider(config)
    monkeypatch.setattr(provider, "get_client", lambda: FakeAnthropicClient())

    events = [
        event
        async for event in provider.chat_completion(
            messages=[{"role": "user", "content": "Think hard"}],
        )
    ]

    types = [e.type for e in events]
    assert StreamEventType.THINKING_DELTA in types

    thinking_event = next(e for e in events if e.type == StreamEventType.THINKING_DELTA)
    assert thinking_event.text_delta is not None
    assert thinking_event.text_delta.content == "reasoning..."
