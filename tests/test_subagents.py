from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

from agentforge_harness.agent.events import AgentEvent
from agentforge_harness.agent.subagent_runner import run_subagent
from agentforge_harness.config.config import Config
from agentforge_harness.tools.base import ToolInvocation
from agentforge_harness.tools.registry import create_default_registry
from agentforge_harness.tools.subagents import SubagentDefinition, SubagentTool


def _definition() -> SubagentDefinition:
    return SubagentDefinition(
        name="explore",
        description="explore the code",
        goal_prompt="You explore.",
        allowed_tools=["read_file"],
        max_turns=5,
        timeout_seconds=30,
    )


async def test_subagent_tool_runs_with_injected_runner(tmp_path: Path):
    seen_prompts: list[str] = []

    async def fake_runner(config: Config, prompt: str) -> AsyncIterator[AgentEvent]:
        seen_prompts.append(prompt)
        yield AgentEvent.text_delta("looking...")
        yield AgentEvent.tool_call_start("c1", "read_file", {"path": "x"})
        yield AgentEvent.text_complete("the answer is 42")
        yield AgentEvent.agents_end("the answer is 42")

    tool = SubagentTool(Config(cwd=tmp_path), _definition(), runner=fake_runner)
    result = await tool.execute(ToolInvocation(params={"goal": "find the answer"}, cwd=tmp_path))

    assert result.success
    assert "the answer is 42" in result.output
    assert "read_file" in result.output  # tools-called summary
    assert seen_prompts and "find the answer" in seen_prompts[0]


async def test_subagent_tool_without_runner_returns_error(tmp_path: Path):
    tool = SubagentTool(Config(cwd=tmp_path), _definition(), runner=None)
    result = await tool.execute(ToolInvocation(params={"goal": "x"}, cwd=tmp_path))

    assert not result.success
    assert "runner is not configured" in (result.error or "")


async def test_subagent_tool_propagates_runner_error(tmp_path: Path):
    async def failing_runner(config: Config, prompt: str) -> AsyncIterator[AgentEvent]:
        yield AgentEvent.agents_error("boom")

    tool = SubagentTool(Config(cwd=tmp_path), _definition(), runner=failing_runner)
    result = await tool.execute(ToolInvocation(params={"goal": "x"}, cwd=tmp_path))

    assert not result.success
    assert "boom" in (result.error or "")


def test_default_registry_wires_subagent_runner(tmp_path: Path):
    registry = create_default_registry(Config(cwd=tmp_path), subagent_runner=run_subagent)

    subagent_tools = [
        tool for tool in registry.get_tools() if isinstance(tool, SubagentTool)
    ]
    assert subagent_tools, "expected default subagent tools to be registered"
    assert all(tool._runner is run_subagent for tool in subagent_tools)
