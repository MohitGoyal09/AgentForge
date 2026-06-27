from __future__ import annotations

import pytest

from agentforge_harness.ui.autocomplete import (
    CompletionItem,
    CompletionState,
    build_completion_state,
)


def test_slash_prefix_suggests_commands() -> None:
    state = build_completion_state("/he", commands=["/help", "/history", "/exit"])
    names = [i.replacement for i in state.items]
    assert "/help" in names


def test_no_prefix_returns_empty() -> None:
    state = build_completion_state("hello world", commands=["/help"])
    assert state.items == ()


def test_exact_slash_shows_all_commands() -> None:
    commands = ["/help", "/exit", "/stats"]
    state = build_completion_state("/", commands=commands)
    replacements = [i.replacement for i in state.items]
    for cmd in commands:
        assert cmd in replacements


def test_select_next_wraps() -> None:
    state = CompletionState(
        items=(
            CompletionItem(display="/help", replacement="/help", start=0, end=1),
            CompletionItem(display="/history", replacement="/history", start=0, end=1),
        )
    )
    assert state.selected_index == 0
    state2 = state.select_next()
    assert state2.selected_index == 1
    state3 = state2.select_next()
    assert state3.selected_index == 0


def test_apply_replaces_text() -> None:
    item = CompletionItem(display="/help", replacement="/help", start=0, end=3)
    result = item.apply("/he")
    assert result == "/help"


def test_select_previous_wraps() -> None:
    state = CompletionState(
        items=(
            CompletionItem(display="/a", replacement="/a", start=0, end=1),
            CompletionItem(display="/b", replacement="/b", start=0, end=1),
            CompletionItem(display="/c", replacement="/c", start=0, end=1),
        )
    )
    state2 = state.select_previous()
    assert state2.selected_index == 2


def test_selected_returns_none_when_empty() -> None:
    state = CompletionState()
    assert state.selected is None


def test_selected_returns_correct_item() -> None:
    item = CompletionItem(display="/help", replacement="/help", start=0, end=1)
    state = CompletionState(items=(item,))
    assert state.selected is item


def test_select_next_on_empty_returns_same() -> None:
    state = CompletionState()
    state2 = state.select_next()
    assert state2.selected_index == 0
    assert state2.items == ()


def test_select_previous_on_empty_returns_same() -> None:
    state = CompletionState()
    state2 = state.select_previous()
    assert state2.selected_index == 0


def test_completion_items_sorted() -> None:
    state = build_completion_state("/", commands=["/zzz", "/aaa", "/mmm"])
    displays = [i.display for i in state.items]
    assert displays == sorted(displays)


def test_case_insensitive_prefix_matching() -> None:
    state = build_completion_state("/HE", commands=["/help", "/hero", "/exit"])
    names = [i.replacement for i in state.items]
    assert "/help" in names
    assert "/hero" in names
    assert "/exit" not in names


def test_non_matching_prefix_returns_empty() -> None:
    state = build_completion_state("/xyz", commands=["/help", "/exit"])
    assert state.items == ()
