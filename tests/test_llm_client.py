from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agentforge_harness.client.llm_client import LLMClient
from agentforge_harness.client.response import StreamEventType
from agentforge_harness.config.config import Config, ModelConfig, ModelProvider


def test_openai_compatible_client_omits_base_url_when_provider_default(monkeypatch):
    captured = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.setattr("agentforge_harness.client.llm_client.AsyncOpenAI", FakeAsyncOpenAI)

    config = Config(cwd=Path("/tmp"), model=ModelConfig(provider=ModelProvider.OPENAI, name="gpt-4o"))
    LLMClient(config).get_client()

    assert captured["api_key"] == "sk-openai"
    assert "base_url" not in captured


def test_openai_compatible_client_uses_configured_base_url(monkeypatch):
    captured = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("API_KEY", "sk-custom")
    monkeypatch.setattr("agentforge_harness.client.llm_client.AsyncOpenAI", FakeAsyncOpenAI)

    config = Config(
        cwd=Path("/tmp"),
        model=ModelConfig(
            provider=ModelProvider.CUSTOM,
            name="local/model",
            base_url="http://localhost:11434/v1",
        ),
    )
    LLMClient(config).get_client()

    assert captured["api_key"] == "sk-custom"
    assert captured["base_url"] == "http://localhost:11434/v1"


async def test_openai_path_sends_temperature_and_max_tokens(monkeypatch):
    """Regression: the OpenAI-compatible path previously omitted temperature
    and max_output_tokens, so configured sampling params were silently dropped."""
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
    client = LLMClient(config)
    monkeypatch.setattr(client, "get_client", lambda: FakeClient())

    _ = [
        event
        async for event in client.chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            stream=False,
        )
    ]

    assert captured["temperature"] == 0.3
    assert captured["max_tokens"] == 512


def test_anthropic_message_conversion_preserves_system_and_tools():
    config = Config(
        cwd=Path("/tmp"),
        model=ModelConfig(provider=ModelProvider.ANTHROPIC, name="claude-3-5-sonnet-latest"),
    )
    client = LLMClient(config)

    system, messages = client._to_anthropic_messages(
        [
            {"role": "system", "content": "You are AgentForge."},
            {"role": "user", "content": "Read file"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"path": "README.MD"}',
                        },
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
    config = Config(cwd=Path("/tmp"))
    client = LLMClient(config)

    tools = client._build_anthropic_tools(
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


async def test_anthropic_provider_emits_text_tool_and_usage_events(monkeypatch):
    captured = {}

    class FakeMessages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(type="text", text="I will read it."),
                    SimpleNamespace(
                        type="tool_use",
                        id="toolu_1",
                        name="read_file",
                        input={"path": "README.MD"},
                    ),
                ],
                usage=SimpleNamespace(input_tokens=12, output_tokens=7),
                stop_reason="tool_use",
            )

    class FakeAnthropicClient:
        messages = FakeMessages()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    config = Config(
        cwd=Path("/tmp"),
        model=ModelConfig(provider=ModelProvider.ANTHROPIC, name="claude-3-5-sonnet-latest"),
    )
    client = LLMClient(config)
    monkeypatch.setattr(client, "get_anthropic_client", lambda: FakeAnthropicClient())

    events = [
        event
        async for event in client.chat_completion(
            messages=[{"role": "user", "content": "Read README"}],
            tools=[
                {
                    "name": "read_file",
                    "description": "Read file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                }
            ],
        )
    ]

    assert captured["model"] == "claude-3-5-sonnet-latest"
    assert captured["tools"][0]["name"] == "read_file"
    assert [event.type for event in events] == [
        StreamEventType.TEXT_DELTA,
        StreamEventType.TOOL_CALL_START,
        StreamEventType.TOOL_CALL_COMPLETE,
        StreamEventType.MESSAGE_COMPLETE,
    ]
    assert events[2].tool_call is not None
    assert events[2].tool_call.arguments == {"path": "README.MD"}
    assert events[3].token_usage is not None
    assert events[3].token_usage.total_tokens == 19
