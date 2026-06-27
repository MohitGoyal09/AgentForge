from __future__ import annotations
import pytest
from agentforge_harness.ui.plain import TUI, PlainTUI


def test_plain_tui_alias():
    assert PlainTUI is TUI


def test_tui_class_has_required_methods():
    assert hasattr(TUI, "show_help")
    assert hasattr(TUI, "show_error")
    assert hasattr(TUI, "begin_assistant")
    assert hasattr(TUI, "stream_assistant_delta")
    assert hasattr(TUI, "end_assistant")
    assert hasattr(TUI, "tool_call_start")
    assert hasattr(TUI, "tool_call_complete")
