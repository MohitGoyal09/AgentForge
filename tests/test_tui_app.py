from __future__ import annotations
import inspect
import pytest
from textual.app import App
from agentforge_harness.ui.tui import AgentForgeTuiApp, run_tui

def test_run_tui_is_coroutine():
    assert inspect.iscoroutinefunction(run_tui)

def test_app_is_textual_app():
    assert issubclass(AgentForgeTuiApp, App)

def test_app_has_required_bindings():
    binding_keys = [b.key for b in AgentForgeTuiApp.BINDINGS]
    assert "ctrl+d" in binding_keys
    assert "ctrl+t" in binding_keys
    assert "ctrl+o" in binding_keys
