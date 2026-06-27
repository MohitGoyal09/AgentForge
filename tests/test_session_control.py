"""Tests for Session introspection accessors and cooperative cancellation."""
from __future__ import annotations

from pathlib import Path

import pytest

from agentforge_harness.agent.agent import Agent
from agentforge_harness.agent.events import AgentEventType
from agentforge_harness.client.response import StreamEvent, StreamEventType, TextDelta, TokenUsage
from agentforge_harness.client.thinking import ThinkingLevel
from agentforge_harness.config.config import Config, ModelConfig
from agentforge_harness.context.manager import ContextManager


# ---------------------------------------------------------------------------
# Fake clients (same style as tests/test_agent_events.py)
# ---------------------------------------------------------------------------

class _SimpleClient:
    async def chat_completion(self, messages, tools=None, **kwargs):
        yield StreamEvent(type=StreamEventType.TEXT_DELTA, text_delta=TextDelta(content="hello"))
        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            token_usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )


class _RecordingClient:
    """Records whether session.is_running was True during chat_completion."""

    def __init__(self, session_ref) -> None:
        self._session = session_ref
        self.seen_running: list[bool] = []

    async def chat_completion(self, messages, tools=None, **kwargs):
        self.seen_running.append(self._session.is_running)
        yield StreamEvent(type=StreamEventType.TEXT_DELTA, text_delta=TextDelta(content="ok"))
        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            token_usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )


class _NeverCalledClient:
    """Raises if chat_completion is ever invoked."""

    async def chat_completion(self, messages, tools=None, **kwargs):
        raise AssertionError("chat_completion should not have been called")
        # make it a generator
        yield  # pragma: no cover


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_agent(tmp_path: Path, client) -> Agent:
    config = Config(cwd=tmp_path, model=ModelConfig(name="test/model"))
    agent = Agent(config)
    session = agent.session
    session.context_manager = ContextManager(config=config, tools=[], skills=[])
    session.client = client
    return agent


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_session_accessors(tmp_path: Path):
    config = Config(cwd=tmp_path, model=ModelConfig(name="test/model"))
    agent = Agent(config)
    session = agent.session
    session.context_manager = ContextManager(config=config, tools=[], skills=[])

    # is_running starts False
    assert session.is_running is False

    # cwd
    assert session.cwd == tmp_path

    # model_name
    assert session.model_name == "test/model"

    # provider_name is a string (value of the ModelProvider enum)
    assert isinstance(session.provider_name, str)
    assert len(session.provider_name) > 0

    # thinking_level is the OFF enum member
    assert session.thinking_level == ThinkingLevel.OFF

    # tool_names is a non-empty list
    names = session.tool_names
    assert isinstance(names, list)
    assert len(names) > 0

    # active_skill_names starts empty
    assert session.active_skill_names == []

    # context_window_tokens matches config
    assert session.context_window_tokens == config.model.context_window

    # context_token_estimate is a non-negative int
    estimate = session.context_token_estimate
    assert isinstance(estimate, int)
    assert estimate >= 0


async def test_is_running_true_during_run(tmp_path: Path):
    config = Config(cwd=tmp_path, model=ModelConfig(name="test/model"))
    agent = Agent(config)
    session = agent.session
    recording_client = _RecordingClient(session)
    session.context_manager = ContextManager(config=config, tools=[], skills=[])
    session.client = recording_client

    # Before the run, is_running is False.
    assert session.is_running is False

    events = [event async for event in agent.run("hi")]

    # The client observed is_running == True during chat_completion.
    assert recording_client.seen_running, "client was never called"
    assert all(recording_client.seen_running), "is_running was not True during stream"

    # After run completes, is_running is reset to False.
    assert session.is_running is False

    # Sanity: run emitted agent_end.
    types = [e.type for e in events]
    assert AgentEventType.AGENT_END in types


async def test_cancel_before_turn_stops_run(tmp_path: Path):
    agent = _make_agent(tmp_path, _NeverCalledClient())
    session = agent.session

    # Signal cancellation before the run starts.
    session.request_cancel()

    events = [event async for event in agent.run("hi")]
    types = [e.type for e in events]

    # Must end with agent_end (run() always emits it via finally).
    assert AgentEventType.AGENT_END in types

    # A text_delta with "[Cancelled]" must have been emitted.
    cancel_deltas = [
        e for e in events
        if e.type == AgentEventType.TEXT_DELTA and "[Cancelled]" in e.data.get("content", "")
    ]
    assert cancel_deltas, "expected a '[Cancelled]' text_delta event"


async def test_reset_cancel_on_new_run(tmp_path: Path):
    agent = _make_agent(tmp_path, _SimpleClient())
    session = agent.session

    # First run — cancelled.
    session.request_cancel()
    first_events = [event async for event in agent.run("hi")]
    first_types = [e.type for e in first_events]

    # First run was cancelled.
    assert any(
        e.type == AgentEventType.TEXT_DELTA and "[Cancelled]" in e.data.get("content", "")
        for e in first_events
    ), "first run should have been cancelled"
    assert AgentEventType.AGENT_END in first_types

    # Second run — no explicit cancel; reset_cancel() was called at start of run().
    second_events = [event async for event in agent.run("hi")]
    second_types = [e.type for e in second_events]

    # Should NOT be cancelled; normal text should arrive.
    assert AgentEventType.AGENT_END in second_types
    cancel_in_second = [
        e for e in second_events
        if e.type == AgentEventType.TEXT_DELTA and "[Cancelled]" in e.data.get("content", "")
    ]
    assert not cancel_in_second, "second run should NOT be cancelled"

    # Verify normal text came through.
    text_deltas = [
        e for e in second_events
        if e.type == AgentEventType.TEXT_DELTA
    ]
    assert text_deltas, "expected text output on non-cancelled run"
