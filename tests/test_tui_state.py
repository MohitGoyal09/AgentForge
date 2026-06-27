from __future__ import annotations

import pytest

from agentforge_harness.ui.state import ChatItem, TuiState


def test_initial_state_is_empty() -> None:
    state = TuiState()
    assert state.items == []
    assert state.assistant_buffer == ""
    assert state.running is False
    assert state.show_thinking is False
    assert state.show_tool_results is True


def test_add_user_message() -> None:
    state = TuiState()
    state.add_user_message("hello")
    assert len(state.items) == 1
    assert state.items[0].role == "user"
    assert state.items[0].text == "hello"


def test_add_assistant_delta_accumulates() -> None:
    state = TuiState()
    state.flush_assistant_delta("hello ")
    state.flush_assistant_delta("world")
    items = [i for i in state.items if i.role == "assistant"]
    assert len(items) == 1
    assert items[0].text == "hello world"


def test_clear_resets_state() -> None:
    state = TuiState()
    state.add_user_message("hi")
    state.running = True
    state.clear()
    assert state.items == []
    assert state.running is False


def test_toggle_thinking() -> None:
    state = TuiState()
    assert state.show_thinking is False
    state.toggle_thinking()
    assert state.show_thinking is True


def test_toggle_tool_results() -> None:
    state = TuiState()
    assert state.show_tool_results is True
    state.toggle_tool_results()
    assert state.show_tool_results is False


def test_flush_thinking_delta_accumulates() -> None:
    state = TuiState()
    state.flush_thinking_delta("thinking ")
    state.flush_thinking_delta("more")
    items = [i for i in state.items if i.role == "thinking"]
    assert len(items) == 1
    assert items[0].text == "thinking more"


def test_add_tool_item_and_update_result() -> None:
    state = TuiState()
    state.add_tool_item(call_id="c1", name="bash", args={"cmd": "ls"})
    assert len(state.items) == 1
    assert state.items[0].role == "tool"
    assert state.items[0].tool_call_id == "c1"
    state.update_tool_result(call_id="c1", output="file1.txt", success=True)
    assert "✓" in state.items[0].text
    assert "file1.txt" in state.items[0].text


def test_update_tool_result_failure_marker() -> None:
    state = TuiState()
    state.add_tool_item(call_id="c2", name="bash", args={})
    state.update_tool_result(call_id="c2", output="error msg", success=False)
    assert "✗" in state.items[0].text


def test_add_error() -> None:
    state = TuiState()
    state.add_error("something went wrong")
    assert len(state.items) == 1
    assert state.items[0].role == "error"
    assert "something went wrong" in state.items[0].text


def test_add_status() -> None:
    state = TuiState()
    state.add_status("initializing…")
    assert state.items[0].role == "status"


def test_finalize_assistant_clears_buffer() -> None:
    state = TuiState()
    state.flush_assistant_delta("partial")
    assert state.assistant_buffer == "partial"
    state.finalize_assistant()
    assert state.assistant_buffer == ""


def test_finalize_thinking_clears_buffer() -> None:
    state = TuiState()
    state.flush_thinking_delta("thought")
    state.finalize_thinking()
    assert state.thinking_buffer == ""
