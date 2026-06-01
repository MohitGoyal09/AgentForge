from __future__ import annotations

from pathlib import Path
from typing import Any

from agentforge_harness.config.config import Config, ModelConfig
from agentforge_harness.hooks.hook_system import HookSystem
from agentforge_harness.safety.output_hygiene import clean_text, clean_tool_result
from agentforge_harness.tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from agentforge_harness.tools.registry import ToolRegistry


FAKE_SECRET = "sk-" + "a" * 32


class NoisyTool(Tool):
    name = "noisy"
    description = "Return control characters, ANSI escapes, and long output."
    kind = ToolKind.READ
    schema = {"type": "object", "properties": {}}

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        return ToolResult.success_result(
            output=(
                "\x1b[31mred\x1b[0m\x00\n"
                f"API_KEY={FAKE_SECRET}\n"
                + "line\n" * 80
            ),
            summary="\x1b[1mnoisy\x1b[0m summary",
            metadata={"note": "safe\x07metadata"},
            next_actions=["Inspect\x08 output"],
            diff_text="+\x1b[32mchanged\x1b[0m\n",
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


def test_clean_text_removes_ansi_and_control_characters():
    cleaned, report = clean_text("\x1b[31mred\x1b[0m\x00\tok\n")

    assert cleaned == "red\tok\n"
    assert report.ansi_sequences_removed == 2
    assert report.control_chars_removed == 1


def test_clean_tool_result_truncates_model_visible_fields():
    result = ToolResult.success_result(
        output="\n".join(f"line {i}" for i in range(200)),
        metadata={"safe": "value"},
    )

    cleaned = clean_tool_result(
        result,
        model_name="test/test-model",
        max_output_tokens=20,
    )

    assert "... [tool output truncated by AgentForge]" in cleaned.output
    assert cleaned.metadata["safe"] == "value"
    assert cleaned.metadata["output_hygiene"]["truncated_fields"]["output"] > 0


async def test_registry_cleans_output_before_redaction_and_hooks(tmp_path: Path):
    config = Config(
        cwd=tmp_path,
        model=ModelConfig(name="test/test-model"),
        max_tool_output_tokens=120,
    )
    registry = ToolRegistry(config)
    registry.register(NoisyTool(config))
    hooks = CapturingHookSystem(config)

    result = await registry.invoke("noisy", {}, tmp_path, hooks)

    assert result.success
    assert "\x1b" not in result.output
    assert "\x00" not in result.output
    assert "\x07" not in str(result.metadata)
    assert "\x08" not in str(result.next_actions)
    assert FAKE_SECRET not in result.output
    assert "[REDACTED:OPENAI_API_KEY]" in result.output
    assert result.metadata["output_hygiene"]["ansi_sequences_removed"] >= 4
    assert result.metadata["output_hygiene"]["control_chars_removed"] >= 3
    assert result.metadata["redaction"]["count"] == 1

    assert hooks.after_tool_results
    hook_result = hooks.after_tool_results[0]
    assert "\x1b" not in hook_result.to_model_output()
    assert FAKE_SECRET not in hook_result.to_model_output()


async def test_registry_can_disable_output_hygiene(tmp_path: Path):
    config = Config(
        cwd=tmp_path,
        model=ModelConfig(name="test/test-model"),
        output_hygiene_enabled=False,
        redaction_enabled=False,
        prompt_injection_protection_enabled=False,
    )
    registry = ToolRegistry(config)
    registry.register(NoisyTool(config))
    hooks = CapturingHookSystem(config)

    result = await registry.invoke("noisy", {}, tmp_path, hooks)

    assert "\x1b" in result.output
    assert "\x00" in result.output
    assert "output_hygiene" not in result.metadata
