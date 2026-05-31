from __future__ import annotations

from pathlib import Path
from typing import Any

from agentforge_harness.config.config import Config
from agentforge_harness.hooks.hook_system import HookSystem
from agentforge_harness.tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from agentforge_harness.tools.registry import ToolRegistry
from agentforge_harness.utils.redaction import redact_text, redact_tool_result


OPENAI_KEY = "sk-" + "a" * 32
OPENROUTER_KEY = "sk-or-v1-" + "b" * 32
ANTHROPIC_KEY = "sk-ant-" + "c" * 32
GITHUB_TOKEN = "ghp_" + "d" * 36
JWT = "eyJ" + "e" * 12 + "." + "f" * 12 + "." + "g" * 12


class SecretEchoTool(Tool):
    name = "secret_echo"
    description = "Return fake secrets for redaction tests."
    kind = ToolKind.READ
    schema = {"type": "object", "properties": {}}

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        return ToolResult.success_result(
            output=f"token={OPENAI_KEY}\nGITHUB_TOKEN={GITHUB_TOKEN}",
            summary=f"summary has {ANTHROPIC_KEY}",
            metadata={
                "nested": {
                    "jwt": JWT,
                    "normal": "safe",
                }
            },
            diff_text=f"+OPENROUTER_API_KEY={OPENROUTER_KEY}\n",
            artifacts=[f"/tmp/{OPENAI_KEY}.txt"],
            next_actions=[f"Do not reveal {GITHUB_TOKEN}"],
        )


class CapturingHookSystem(HookSystem):
    def __init__(self, config: Config):
        super().__init__(config)
        self.after_tool_results: list[ToolResult] = []

    async def trigger_before_tool(self, tool_name: str, tool_params: dict[str, Any]) -> None:
        return None

    async def trigger_after_tool(
        self,
        tool_name: str,
        tool_params: dict[str, Any],
        tool_result: ToolResult,
    ) -> None:
        self.after_tool_results.append(tool_result)


def test_redact_text_detects_common_secret_shapes():
    text = "\n".join(
        [
            f"openai={OPENAI_KEY}",
            f"openrouter={OPENROUTER_KEY}",
            f"anthropic={ANTHROPIC_KEY}",
            f"github={GITHUB_TOKEN}",
            f"jwt={JWT}",
            "API_KEY=plain-secret-value",
            "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
        ]
    )

    redacted, report = redact_text(text)

    assert OPENAI_KEY not in redacted
    assert OPENROUTER_KEY not in redacted
    assert ANTHROPIC_KEY not in redacted
    assert GITHUB_TOKEN not in redacted
    assert JWT not in redacted
    assert "plain-secret-value" not in redacted
    assert "abc" not in redacted
    assert report.count >= 7
    assert report.kinds["private_key"] == 1


def test_redact_tool_result_redacts_model_visible_fields():
    result = ToolResult.success_result(
        output=f"output {OPENAI_KEY}",
        summary=f"summary {ANTHROPIC_KEY}",
        metadata={"token": GITHUB_TOKEN, "safe": "value"},
        diff_text=f"+secret={JWT}",
    )

    redacted = redact_tool_result(result)
    model_output = redacted.to_model_output()

    assert OPENAI_KEY not in model_output
    assert ANTHROPIC_KEY not in model_output
    assert GITHUB_TOKEN not in str(redacted.metadata)
    assert JWT not in (redacted.diff_text or "")
    assert redacted.metadata["safe"] == "value"
    assert redacted.metadata["redaction"]["count"] >= 4


async def test_tool_registry_redacts_before_hooks_and_return(tmp_path: Path):
    config = Config(cwd=tmp_path, model_name="test/test-model")
    registry = ToolRegistry(config)
    registry.register(SecretEchoTool(config))
    hooks = CapturingHookSystem(config)

    result = await registry.invoke(
        "secret_echo",
        {},
        tmp_path,
        hooks,
    )

    assert result.success
    assert OPENAI_KEY not in result.to_model_output()
    assert OPENROUTER_KEY not in (result.diff_text or "")
    assert GITHUB_TOKEN not in result.to_model_output()
    assert result.metadata["redaction"]["count"] >= 6

    assert hooks.after_tool_results
    hook_result = hooks.after_tool_results[0]
    assert OPENAI_KEY not in hook_result.to_model_output()
    assert hook_result.metadata["redaction"]["count"] == result.metadata["redaction"]["count"]


async def test_tool_registry_can_disable_redaction(tmp_path: Path):
    config = Config(cwd=tmp_path, model_name="test/test-model", redaction_enabled=False)
    registry = ToolRegistry(config)
    registry.register(SecretEchoTool(config))
    hooks = CapturingHookSystem(config)

    result = await registry.invoke(
        "secret_echo",
        {},
        tmp_path,
        hooks,
    )

    assert OPENAI_KEY in result.to_model_output()
    assert "redaction" not in result.metadata
