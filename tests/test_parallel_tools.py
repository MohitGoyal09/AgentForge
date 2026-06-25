from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel

from agentforge_harness.agent.agent import Agent
from agentforge_harness.agent.events import AgentEventType
from agentforge_harness.agent.modes import AgentMode
from agentforge_harness.client.response import (
    StreamEvent,
    StreamEventType,
    TextDelta,
    TokenUsage,
    ToolCall,
)
from agentforge_harness.config.config import Config, ModelConfig
from agentforge_harness.context.manager import ContextManager
from agentforge_harness.tools.base import Tool, ToolInvocation, ToolKind, ToolResult


class _ProbeParams(BaseModel):
    pass


class _ConcurrencyProbeTool(Tool):
    """READ tool that records the peak number of concurrent executions."""

    name = "probe"
    description = "probe"
    kind = ToolKind.READ

    def __init__(self, config):
        super().__init__(config)
        self.active = 0
        self.max_active = 0

    @property
    def schema(self):
        return _ProbeParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.02)
        self.active -= 1
        return ToolResult.success_result("ok")


def _agent(tmp_path: Path, mode: AgentMode = AgentMode.BUILD) -> Agent:
    config = Config(cwd=tmp_path, model=ModelConfig(name="test/model"))
    agent = Agent(config)
    agent.session.mode = mode
    agent.session.context_manager = ContextManager(config=config, tools=[], skills=[])
    return agent


def test_can_parallelize_only_read_batches_in_build_mode(tmp_path: Path):
    agent = _agent(tmp_path)

    two_reads = [ToolCall("c1", "read_file", {}), ToolCall("c2", "glob", {})]
    assert agent._can_parallelize_tools(two_reads) is True

    # single call — nothing to parallelize
    assert agent._can_parallelize_tools([ToolCall("c1", "read_file", {})]) is False

    # mixed read + write — falls back to sequential
    mixed = [ToolCall("c1", "read_file", {}), ToolCall("c2", "write_file", {})]
    assert agent._can_parallelize_tools(mixed) is False


def test_plan_mode_never_parallelizes(tmp_path: Path):
    agent = _agent(tmp_path, mode=AgentMode.PLAN)
    two_reads = [ToolCall("c1", "read_file", {}), ToolCall("c2", "grep", {})]
    assert agent._can_parallelize_tools(two_reads) is False


class _TwoReadsThenDone:
    def __init__(self) -> None:
        self.calls = 0

    async def chat_completion(self, messages, tools=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            yield StreamEvent(
                type=StreamEventType.TOOL_CALL_COMPLETE,
                tool_call=ToolCall(call_id="c1", name="probe", arguments={}),
            )
            yield StreamEvent(
                type=StreamEventType.TOOL_CALL_COMPLETE,
                tool_call=ToolCall(call_id="c2", name="probe", arguments={}),
            )
            yield StreamEvent(
                type=StreamEventType.MESSAGE_COMPLETE,
                token_usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            )
            return
        yield StreamEvent(type=StreamEventType.TEXT_DELTA, text_delta=TextDelta(content="done"))
        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            token_usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )


async def test_read_only_batch_runs_concurrently(tmp_path: Path):
    agent = _agent(tmp_path)
    probe = _ConcurrencyProbeTool(agent.config)
    agent.session.tool_registry.register(probe)
    agent.session.client = _TwoReadsThenDone()

    events = [event async for event in agent.run("go")]

    # Both probe invocations were in flight at the same time.
    assert probe.max_active == 2

    completes = [
        e
        for e in events
        if e.type == AgentEventType.TOOL_CALL_COMPLETE and e.name == "probe"
    ]
    assert len(completes) == 2
    assert all(e.result.success for e in completes)
