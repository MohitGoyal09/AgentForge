from __future__ import annotations

from pathlib import Path

from agentforge_harness.client.llm_client import LLMClient
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
