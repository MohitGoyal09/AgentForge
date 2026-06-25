from __future__ import annotations

from typing import AsyncIterator

from agentforge_harness.agent.events import AgentEvent
from agentforge_harness.config.config import Config


async def run_subagent(config: Config, prompt: str) -> AsyncIterator[AgentEvent]:
    """Default subagent runner: spin up an Agent and stream its events.

    Defined in the agent layer and injected into SubagentTool by the session
    composition root, so the tools layer never imports the Agent class. The
    Agent import is local to keep this module free of a load-time import cycle
    (agent -> session -> subagent_runner).
    """
    from agentforge_harness.agent.agent import Agent

    async with Agent(config) as agent:
        async for event in agent.run(prompt):
            yield event
