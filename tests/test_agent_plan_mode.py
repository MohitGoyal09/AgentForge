from __future__ import annotations

from pathlib import Path

from agentforge_harness.agent.agent import Agent
from agentforge_harness.agent.events import AgentEventType
from agentforge_harness.agent.modes import AgentMode
from agentforge_harness.client.response import StreamEvent, StreamEventType, TextDelta, TokenUsage, ToolCall
from agentforge_harness.config.config import Config, ModelConfig
from agentforge_harness.context.manager import ContextManager


class RepeatingPlanClient:
    def __init__(self) -> None:
        self.calls = 0
        self.tools_seen: list[list[dict] | None] = []

    async def chat_completion(self, messages, tools=None, **kwargs):
        self.tools_seen.append(tools)
        self.calls += 1

        if tools:
            yield StreamEvent(
                type=StreamEventType.TOOL_CALL_COMPLETE,
                tool_call=ToolCall(
                    call_id=f"call-{self.calls}",
                    name="glob",
                    arguments={"pattern": "**/*template*"},
                ),
            )
            yield StreamEvent(
                type=StreamEventType.MESSAGE_COMPLETE,
                token_usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            )
            return

        yield StreamEvent(
            type=StreamEventType.TEXT_DELTA,
            text_delta=TextDelta(content="Final plan: inspect, design, then switch to /build."),
        )
        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            token_usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )


async def test_plan_mode_stops_repeated_tool_loop_and_forces_text_response(tmp_path: Path):
    config = Config(cwd=tmp_path, model=ModelConfig(name="test/model"), max_turns=20)
    agent = Agent(config)
    session = agent.session
    session.mode = AgentMode.PLAN
    session.context_manager = ContextManager(
        config=config,
        tools=session.tool_registry.get_tools(mode=AgentMode.PLAN),
        skills=[],
        mode=AgentMode.PLAN,
    )
    session.context_manager.add_user_message("Build a landing page, but plan first.")
    fake_client = RepeatingPlanClient()
    session.client = fake_client

    events = [event async for event in agent._agentic_loop()]

    text = "".join(
        event.data.get("content", "")
        for event in events
        if event.type == AgentEventType.TEXT_DELTA
    )

    assert "Plan mode stopped repeated tool exploration" in text
    assert "Final plan" in text
    assert fake_client.tools_seen[-1] is None
