from __future__ import annotations

from pathlib import Path

import pytest

from agentforge_harness.agent.agent import Agent
from agentforge_harness.agent.events import AgentEvent, AgentEventType
from agentforge_harness.client.response import StreamEvent, StreamEventType, TextDelta, TokenUsage
from agentforge_harness.config.config import Config, ModelConfig
from agentforge_harness.context.manager import ContextManager


class _CapturingPersistence:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def append_event(self, session_id, turn, sequence, event_type, payload):
        self.events.append((event_type, payload))


class _SimpleClient:
    async def chat_completion(self, messages, tools=None, **kwargs):
        yield StreamEvent(type=StreamEventType.TEXT_DELTA, text_delta=TextDelta(content="hello world"))
        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            token_usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )


class _FlakyThenOkClient:
    def __init__(self) -> None:
        self.calls = 0

    async def chat_completion(self, messages, tools=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            yield StreamEvent(type=StreamEventType.ERROR, error="rate limited")
            return
        yield StreamEvent(type=StreamEventType.TEXT_DELTA, text_delta=TextDelta(content="ok"))
        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            token_usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )


def _agent_with(tmp_path: Path, client) -> tuple[Agent, _CapturingPersistence]:
    config = Config(cwd=tmp_path, model=ModelConfig(name="test/model"))
    agent = Agent(config)
    session = agent.session
    session.context_manager = ContextManager(config=config, tools=[], skills=[])
    session.client = client
    cap = _CapturingPersistence()
    session.persistence = cap
    return agent, cap


async def test_run_emits_message_lifecycle(tmp_path: Path):
    agent, _ = _agent_with(tmp_path, _SimpleClient())

    events = [event async for event in agent.run("hi")]
    types = [event.type for event in events]

    assert types[0] == AgentEventType.AGENT_START
    assert types[-1] == AgentEventType.AGENT_END
    assert AgentEventType.MESSAGE_START in types
    assert AgentEventType.MESSAGE_END in types

    message_end = next(e for e in events if e.type == AgentEventType.MESSAGE_END)
    assert message_end.content == "hello world"


async def test_run_records_events_in_persistence(tmp_path: Path):
    """Recording moved into Agent.run(), so embedded usage logs without the CLI."""
    agent, cap = _agent_with(tmp_path, _SimpleClient())

    _ = [event async for event in agent.run("hi")]

    recorded_types = [event_type for event_type, _ in cap.events]
    assert "agent_start" in recorded_types
    assert "message_start" in recorded_types
    assert "text_complete" in recorded_types
    assert "message_end" in recorded_types
    assert "agent_end" in recorded_types


async def test_record_events_flag_disables_persistence(tmp_path: Path):
    config = Config(cwd=tmp_path, model=ModelConfig(name="test/model"))
    agent = Agent(config, record_events=False)
    cap = _CapturingPersistence()
    agent.session.persistence = cap

    agent._record(AgentEvent.text_delta("x"))

    assert cap.events == []


class _AllErrorsClient:
    async def chat_completion(self, messages, tools=None, **kwargs):
        yield StreamEvent(type=StreamEventType.ERROR, error="down")


async def test_message_frame_is_closed_when_all_models_fail(tmp_path: Path, monkeypatch):
    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr("agentforge_harness.agent.agent.asyncio.sleep", _no_sleep)
    agent, _ = _agent_with(tmp_path, _AllErrorsClient())

    events = [event async for event in agent.run("hi")]
    types = [event.type for event in events]

    # Every message_start must be balanced by a message_end, even on the
    # all-models-failed path that ends in an agent_error.
    assert types.count(AgentEventType.MESSAGE_START) == types.count(AgentEventType.MESSAGE_END)
    assert AgentEventType.AGENT_ERROR in types


async def test_retry_emits_structured_retry_event(tmp_path: Path, monkeypatch):
    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr("agentforge_harness.agent.agent.asyncio.sleep", _no_sleep)
    agent, _ = _agent_with(tmp_path, _FlakyThenOkClient())

    events = [event async for event in agent.run("hi")]
    retry_events = [e for e in events if e.type == AgentEventType.RETRY]

    assert retry_events, "expected a RETRY event after a transient provider error"
    assert retry_events[0].model == "test/model"
    assert "rate limited" in retry_events[0].error


class _ThinkingThenTextClient:
    async def chat_completion(self, messages, tools=None, **kwargs):
        yield StreamEvent(
            type=StreamEventType.THINKING_DELTA,
            text_delta=TextDelta(content="reasoning..."),
        )
        yield StreamEvent(type=StreamEventType.TEXT_DELTA, text_delta=TextDelta(content="answer"))
        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            token_usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )


async def test_thinking_delta_is_emitted(tmp_path: Path):
    agent, _ = _agent_with(tmp_path, _ThinkingThenTextClient())

    events = [event async for event in agent.run("hi")]
    thinking_events = [e for e in events if e.type == AgentEventType.THINKING_DELTA]

    assert thinking_events, "expected at least one THINKING_DELTA event"
    assert thinking_events[0].content == "reasoning..."


class _PartialThenErrorThenOkClient:
    """First call: emits partial text then errors. Second call: succeeds fully."""

    def __init__(self) -> None:
        self.calls = 0

    async def chat_completion(self, messages, tools=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            yield StreamEvent(type=StreamEventType.TEXT_DELTA, text_delta=TextDelta(content="Hello"))
            yield StreamEvent(type=StreamEventType.ERROR, error="stream cut")
            return
        yield StreamEvent(type=StreamEventType.TEXT_DELTA, text_delta=TextDelta(content="Hello world"))
        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            token_usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )


async def test_retry_does_not_restream_partial_text(tmp_path: Path, monkeypatch):
    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr("agentforge_harness.agent.agent.asyncio.sleep", _no_sleep)
    agent, _ = _agent_with(tmp_path, _PartialThenErrorThenOkClient())

    events = [event async for event in agent.run("hi")]
    text_deltas = [e for e in events if e.type == AgentEventType.TEXT_DELTA]
    delta_contents = [e.content for e in text_deltas if not e.content.startswith("\n[")]

    # The partial "Hello" from the failed first attempt should appear exactly
    # once as a raw TEXT_DELTA (yielded during that attempt).  The second call
    # returns "Hello world" as a single delta — also exactly once.  What we
    # must NOT see is a standalone "Hello" delta emitted a second time as a
    # replay of the first attempt's partial output.
    standalone_hello = [c for c in delta_contents if c == "Hello"]
    assert len(standalone_hello) == 1, (
        f"Partial text 'Hello' was re-emitted. Non-noise TEXT_DELTA contents: {delta_contents!r}"
    )

    # The run must still complete (AGENT_END present)
    types = [e.type for e in events]
    assert AgentEventType.AGENT_END in types
