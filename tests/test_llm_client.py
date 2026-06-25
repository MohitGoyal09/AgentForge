from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from agentforge_harness.client.llm_client import LLMClient
from agentforge_harness.client.providers import (
    AnthropicProvider,
    OpenAICompatibleProvider,
    create_provider,
)
from agentforge_harness.client.providers.base import BaseProvider
from agentforge_harness.client.providers.fake import FakeProvider
from agentforge_harness.client.response import StreamEvent, StreamEventType, TextDelta
from agentforge_harness.config.config import Config, ModelConfig, ModelProvider


# --------------------------------------------------------------------------- #
# Provider resolution
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "provider,expected",
    [
        (ModelProvider.OPENAI, OpenAICompatibleProvider),
        (ModelProvider.OPENROUTER, OpenAICompatibleProvider),
        (ModelProvider.CUSTOM, OpenAICompatibleProvider),
        (ModelProvider.ANTHROPIC, AnthropicProvider),
    ],
)
def test_create_provider_resolves_expected_adapter(provider, expected):
    config = Config(cwd=Path("/tmp"), model=ModelConfig(provider=provider, name="m", base_url="http://x"))
    assert isinstance(create_provider(config), expected)


def test_llm_client_delegates_to_resolved_provider():
    config = Config(cwd=Path("/tmp"), model=ModelConfig(provider=ModelProvider.ANTHROPIC, name="claude"))
    client = LLMClient(config)
    assert isinstance(client.provider, AnthropicProvider)


# --------------------------------------------------------------------------- #
# OpenAI-compatible adapter
# --------------------------------------------------------------------------- #


def test_openai_compatible_client_omits_base_url_when_provider_default(monkeypatch):
    captured = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.setattr(
        "agentforge_harness.client.providers.openai_compatible.AsyncOpenAI", FakeAsyncOpenAI
    )

    config = Config(cwd=Path("/tmp"), model=ModelConfig(provider=ModelProvider.OPENAI, name="gpt-4o"))
    OpenAICompatibleProvider(config).get_client()

    assert captured["api_key"] == "sk-openai"
    assert "base_url" not in captured


def test_openai_compatible_client_uses_configured_base_url(monkeypatch):
    captured = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("API_KEY", "sk-custom")
    monkeypatch.setattr(
        "agentforge_harness.client.providers.openai_compatible.AsyncOpenAI", FakeAsyncOpenAI
    )

    config = Config(
        cwd=Path("/tmp"),
        model=ModelConfig(
            provider=ModelProvider.CUSTOM,
            name="local/model",
            base_url="http://localhost:11434/v1",
        ),
    )
    OpenAICompatibleProvider(config).get_client()

    assert captured["api_key"] == "sk-custom"
    assert captured["base_url"] == "http://localhost:11434/v1"


async def test_openai_path_sends_temperature_and_max_tokens(monkeypatch):
    captured = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="hi", tool_calls=None),
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

    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    config = Config(
        cwd=Path("/tmp"),
        model=ModelConfig(
            provider=ModelProvider.OPENAI,
            name="gpt-4o",
            temperature=0.3,
            max_output_tokens=512,
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

    assert captured["temperature"] == 0.3
    assert captured["max_tokens"] == 512


# --------------------------------------------------------------------------- #
# Anthropic adapter — message conversion + tool schema
# --------------------------------------------------------------------------- #


def test_anthropic_message_conversion_preserves_system_and_tools():
    config = Config(
        cwd=Path("/tmp"),
        model=ModelConfig(provider=ModelProvider.ANTHROPIC, name="claude-3-5-sonnet-latest"),
    )
    provider = AnthropicProvider(config)

    system, messages = provider._to_anthropic_messages(
        [
            {"role": "system", "content": "You are AgentForge."},
            {"role": "user", "content": "Read file"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "read_file", "arguments": '{"path": "README.MD"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "file contents"},
        ]
    )

    assert system == "You are AgentForge."
    assert messages[0] == {"role": "user", "content": "Read file"}
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"][0]["type"] == "tool_use"
    assert messages[1]["content"][0]["input"] == {"path": "README.MD"}
    assert messages[2]["role"] == "user"
    assert messages[2]["content"][0]["type"] == "tool_result"


def test_anthropic_tool_schema_uses_input_schema():
    config = Config(cwd=Path("/tmp"), model=ModelConfig(provider=ModelProvider.ANTHROPIC, name="claude"))
    provider = AnthropicProvider(config)

    tools = provider._build_anthropic_tools(
        [
            {
                "name": "read_file",
                "description": "Read a file",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
            }
        ]
    )

    assert tools == [
        {
            "name": "read_file",
            "description": "Read a file",
            "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
        }
    ]


# --------------------------------------------------------------------------- #
# Anthropic adapter — real streaming
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


def _anthropic_stream_script():
    return [
        SimpleNamespace(type="message_start", message=SimpleNamespace(usage=SimpleNamespace(input_tokens=12))),
        SimpleNamespace(
            type="content_block_delta",
            index=0,
            delta=SimpleNamespace(type="text_delta", text="I will read it."),
        ),
        SimpleNamespace(
            type="content_block_start",
            index=1,
            content_block=SimpleNamespace(type="tool_use", id="toolu_1", name="read_file"),
        ),
        SimpleNamespace(
            type="content_block_delta",
            index=1,
            delta=SimpleNamespace(type="input_json_delta", partial_json='{"path": '),
        ),
        SimpleNamespace(
            type="content_block_delta",
            index=1,
            delta=SimpleNamespace(type="input_json_delta", partial_json='"README.MD"}'),
        ),
        SimpleNamespace(type="content_block_stop", index=1),
        SimpleNamespace(
            type="message_delta",
            delta=SimpleNamespace(stop_reason="tool_use"),
            usage=SimpleNamespace(output_tokens=7),
        ),
    ]


async def test_anthropic_streaming_emits_incremental_text_tool_and_usage(monkeypatch):
    captured = {}

    class FakeMessages:
        def stream(self, **kwargs):
            captured.update(kwargs)
            return _FakeStreamManager(_anthropic_stream_script())

    class FakeAnthropicClient:
        messages = FakeMessages()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    config = Config(
        cwd=Path("/tmp"),
        model=ModelConfig(provider=ModelProvider.ANTHROPIC, name="claude-3-5-sonnet-latest"),
    )
    provider = AnthropicProvider(config)
    monkeypatch.setattr(provider, "get_client", lambda: FakeAnthropicClient())

    events = [
        event
        async for event in provider.chat_completion(
            messages=[{"role": "user", "content": "Read README"}],
            tools=[
                {
                    "name": "read_file",
                    "description": "Read file",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
                }
            ],
        )
    ]

    assert captured["model"] == "claude-3-5-sonnet-latest"
    assert captured["tools"][0]["name"] == "read_file"

    types = [event.type for event in events]
    # Real streaming: text arrives as a delta before the tool call resolves.
    assert types == [
        StreamEventType.TEXT_DELTA,
        StreamEventType.TOOL_CALL_START,
        StreamEventType.TOOL_CALL_DELTA,
        StreamEventType.TOOL_CALL_DELTA,
        StreamEventType.TOOL_CALL_COMPLETE,
        StreamEventType.MESSAGE_COMPLETE,
    ]

    complete = next(e for e in events if e.type == StreamEventType.TOOL_CALL_COMPLETE)
    assert complete.tool_call is not None
    assert complete.tool_call.arguments == {"path": "README.MD"}

    final = events[-1]
    assert final.finish_reason == "tool_use"
    assert final.token_usage is not None
    assert final.token_usage.total_tokens == 19


# --------------------------------------------------------------------------- #
# Shared retry loop (BaseProvider)
# --------------------------------------------------------------------------- #


class _BoomError(Exception):
    pass


class _FlakyProvider(BaseProvider):
    def __init__(self, config, fail_times):
        super().__init__(config)
        self._fail_times = fail_times
        self.attempts = 0

    def retryable_exceptions(self):
        return (_BoomError,)

    async def _generate(self, messages, tools, stream, model):
        self.attempts += 1
        if self.attempts <= self._fail_times:
            raise _BoomError("transient")
        yield StreamEvent(type=StreamEventType.TEXT_DELTA, text_delta=TextDelta(content="ok"))
        yield StreamEvent(type=StreamEventType.MESSAGE_COMPLETE)


async def test_retry_loop_recovers_after_transient_failures(monkeypatch):
    monkeypatch.setattr(BaseProvider, "_backoff_seconds", lambda self, attempt: 0)
    provider = _FlakyProvider(Config(cwd=Path("/tmp")), fail_times=2)

    events = [e async for e in provider.chat_completion(messages=[], max_retries=3)]

    assert provider.attempts == 3
    assert [e.type for e in events] == [StreamEventType.TEXT_DELTA, StreamEventType.MESSAGE_COMPLETE]


async def test_retry_loop_emits_error_event_after_exhaustion(monkeypatch):
    monkeypatch.setattr(BaseProvider, "_backoff_seconds", lambda self, attempt: 0)
    provider = _FlakyProvider(Config(cwd=Path("/tmp")), fail_times=10)

    events = [e async for e in provider.chat_completion(messages=[], max_retries=2)]

    assert provider.attempts == 3  # initial + 2 retries
    assert len(events) == 1
    assert events[0].type == StreamEventType.ERROR
    assert "transient" in events[0].error


# --------------------------------------------------------------------------- #
# FakeProvider
# --------------------------------------------------------------------------- #


async def test_fake_provider_replays_events_and_records_calls():
    scripted = [
        StreamEvent(type=StreamEventType.TEXT_DELTA, text_delta=TextDelta(content="hello")),
        StreamEvent(type=StreamEventType.MESSAGE_COMPLETE),
    ]
    provider = FakeProvider(events=scripted)

    events = [
        e
        async for e in provider.chat_completion(
            messages=[{"role": "user", "content": "hi"}], model="m"
        )
    ]

    assert [e.type for e in events] == [StreamEventType.TEXT_DELTA, StreamEventType.MESSAGE_COMPLETE]
    assert provider.calls[0]["model"] == "m"
    assert provider.calls[0]["messages"] == [{"role": "user", "content": "hi"}]
