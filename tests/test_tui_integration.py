from __future__ import annotations
import inspect
import pytest
from unittest.mock import MagicMock
from agentforge_harness.ui import run_tui
from agentforge_harness.ui.plain import TUI as PlainTUI
from agentforge_harness.ui.tui import AgentForgeTuiApp
from agentforge_harness.ui.state import TuiState
from agentforge_harness.ui.adapter import TuiEventAdapter
from agentforge_harness.ui.config import DEFAULT_THEME
from agentforge_harness.ui.autocomplete import build_completion_state
from agentforge_harness.agent.events import AgentEventType

def test_ui_package_exports():
    assert inspect.iscoroutinefunction(run_tui)

def test_plain_tui_still_works():
    assert hasattr(PlainTUI, "show_error")
    assert hasattr(PlainTUI, "show_help")

def test_event_pipeline_end_to_end():
    state = TuiState()
    adapter = TuiEventAdapter(state)
    def evt(t, data=None):
        m = MagicMock()
        m.type = t
        m.data = data or {}
        return m
    adapter.apply(evt(AgentEventType.AGENT_START))
    assert state.running is True
    adapter.apply(evt(AgentEventType.TEXT_DELTA, {"content": "hello "}))
    adapter.apply(evt(AgentEventType.TEXT_DELTA, {"content": "world"}))
    adapter.apply(evt(AgentEventType.AGENT_END, {"content": "hello world"}))
    assert state.running is False
    assistant_items = [i for i in state.items if i.role == "assistant"]
    assert len(assistant_items) == 1
    assert "hello" in assistant_items[0].text

def test_autocomplete_slash_commands():
    cmds = ["/help", "/exit", "/stats", "/history"]
    state = build_completion_state("/hi", commands=cmds)
    assert len(state.items) == 1
    assert state.items[0].replacement == "/history"

def test_state_theme_role_coverage():
    roles = ["user", "assistant", "tool", "error", "thinking", "status"]
    for role in roles:
        assert role in DEFAULT_THEME.role_styles, f"Missing theme for role: {role}"
