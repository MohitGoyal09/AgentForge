from __future__ import annotations

import pytest

from agentforge_harness.ui.config import DEFAULT_THEME, TuiKeybindings, TuiTheme


def test_default_theme_is_frozen() -> None:
    with pytest.raises((AttributeError, TypeError)):
        DEFAULT_THEME.screen_background = "red"  # type: ignore[misc]


def test_theme_has_role_styles() -> None:
    for role in ["user", "assistant", "tool", "error", "thinking"]:
        assert role in DEFAULT_THEME.role_styles


def test_default_keybindings() -> None:
    kb = TuiKeybindings()
    assert kb.cancel == "escape"
    assert kb.queue_steer == "alt+enter"
    assert kb.toggle_thinking == "ctrl+t"
    assert kb.toggle_tool_results == "ctrl+o"
    assert kb.session_picker == "ctrl+r"


def test_theme_css_variables_returns_dict() -> None:
    css_vars = DEFAULT_THEME.css_variables()
    assert isinstance(css_vars, dict)
    assert "af-background" in css_vars
    assert "af-text" in css_vars
    assert "af-accent" in css_vars
    assert "af-prompt-border" in css_vars


def test_theme_css_variables_values_match_theme() -> None:
    css_vars = DEFAULT_THEME.css_variables()
    assert css_vars["af-background"] == DEFAULT_THEME.screen_background
    assert css_vars["af-accent"] == DEFAULT_THEME.accent


def test_role_style_is_frozen() -> None:
    style = DEFAULT_THEME.role_styles["user"]
    with pytest.raises((AttributeError, TypeError)):
        style.border = "red"  # type: ignore[misc]


def test_keybindings_is_frozen() -> None:
    kb = TuiKeybindings()
    with pytest.raises((AttributeError, TypeError)):
        kb.cancel = "q"  # type: ignore[misc]


def test_keybindings_all_defaults_set() -> None:
    kb = TuiKeybindings()
    assert kb.branch_picker == "ctrl+b"
    assert kb.quit == "ctrl+d"
    assert kb.accept_completion == "tab"
    assert kb.completion_next == "down"
    assert kb.completion_previous == "up"


def test_theme_has_status_role_style() -> None:
    assert "status" in DEFAULT_THEME.role_styles
