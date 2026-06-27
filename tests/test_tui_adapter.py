from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from agentforge_harness.agent.events import AgentEventType
from agentforge_harness.ui.adapter import TuiEventAdapter
from agentforge_harness.ui.state import TuiState


def _make_event(event_type: AgentEventType, data: dict | None = None) -> MagicMock:
    evt = MagicMock()
    evt.type = event_type
    evt.data = data or {}
    return evt


def test_agents_start_sets_running() -> None:
    state = TuiState()
    adapter = TuiEventAdapter(state)
    adapter.apply(_make_event(AgentEventType.AGENT_START))
    assert state.running is True


def test_agents_end_clears_running() -> None:
    state = TuiState()
    state.running = True
    adapter = TuiEventAdapter(state)
    adapter.apply(_make_event(AgentEventType.AGENT_END, {"content": "done"}))
    assert state.running is False


def test_text_delta_appends_to_buffer() -> None:
    state = TuiState()
    adapter = TuiEventAdapter(state)
    adapter.apply(_make_event(AgentEventType.AGENT_START))
    adapter.apply(_make_event(AgentEventType.TEXT_DELTA, {"content": "hello"}))
    adapter.apply(_make_event(AgentEventType.TEXT_DELTA, {"content": " world"}))
    items = [i for i in state.items if i.role == "assistant"]
    assert items[0].text == "hello world"


def test_agent_error_adds_error_item() -> None:
    state = TuiState()
    adapter = TuiEventAdapter(state)
    adapter.apply(_make_event(AgentEventType.AGENT_ERROR, {"error": "boom"}))
    errors = [i for i in state.items if i.role == "error"]
    assert len(errors) == 1
    assert "boom" in errors[0].text


def test_text_complete_clears_buffer() -> None:
    state = TuiState()
    adapter = TuiEventAdapter(state)
    adapter.apply(_make_event(AgentEventType.TEXT_DELTA, {"content": "hi"}))
    assert state.assistant_buffer == "hi"
    adapter.apply(_make_event(AgentEventType.TEXT_COMPLETE, {"content": "hi"}))
    assert state.assistant_buffer == ""


def test_thinking_delta_appends() -> None:
    state = TuiState()
    adapter = TuiEventAdapter(state)
    adapter.apply(_make_event(AgentEventType.THINKING_DELTA, {"content": "step 1"}))
    adapter.apply(_make_event(AgentEventType.THINKING_DELTA, {"content": " step 2"}))
    items = [i for i in state.items if i.role == "thinking"]
    assert items[0].text == "step 1 step 2"


def test_tool_call_start_adds_tool_item() -> None:
    state = TuiState()
    adapter = TuiEventAdapter(state)
    adapter.apply(_make_event(
        AgentEventType.TOOL_CALL_START,
        {"call_id": "t1", "name": "bash", "arguments": {"cmd": "ls"}},
    ))
    items = [i for i in state.items if i.role == "tool"]
    assert len(items) == 1
    assert "bash" in items[0].text
    assert items[0].tool_call_id == "t1"


def test_tool_call_complete_updates_result() -> None:
    state = TuiState()
    adapter = TuiEventAdapter(state)
    adapter.apply(_make_event(
        AgentEventType.TOOL_CALL_START,
        {"call_id": "t2", "name": "read", "arguments": {}},
    ))
    adapter.apply(_make_event(
        AgentEventType.TOOL_CALL_COMPLETE,
        {"call_id": "t2", "output": "contents", "success": True},
    ))
    items = [i for i in state.items if i.role == "tool"]
    assert "✓" in items[0].text


def test_agent_error_sets_running_false() -> None:
    state = TuiState()
    state.running = True
    adapter = TuiEventAdapter(state)
    adapter.apply(_make_event(AgentEventType.AGENT_ERROR, {"error": "crash"}))
    assert state.running is False
