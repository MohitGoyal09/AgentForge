from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TuiRoleStyle:
    border: str
    body: str


@dataclass(frozen=True, slots=True)
class TuiTheme:
    name: str
    screen_background: str
    screen_text: str
    accent: str
    prompt_border_focused: str
    role_styles: dict[str, TuiRoleStyle]

    def css_variables(self) -> dict[str, str]:
        return {
            "af-background": self.screen_background,
            "af-text": self.screen_text,
            "af-accent": self.accent,
            "af-prompt-border": self.prompt_border_focused,
        }


DEFAULT_THEME = TuiTheme(
    name="af-dark",
    screen_background="#1a1a2e",
    screen_text="#e0e0e0",
    accent="#4ec9b0",
    prompt_border_focused="#4ec9b0",
    role_styles={
        "user":      TuiRoleStyle(border="#7c8ea6", body="#d8dee9"),
        "assistant": TuiRoleStyle(border="#4ec9b0", body="#d8dee9"),
        "tool":      TuiRoleStyle(border="#8a7a52", body="#cbd5e1"),
        "error":     TuiRoleStyle(border="#ff4f4f", body="#ffb4b4"),
        "thinking":  TuiRoleStyle(border="#4b5563", body="#9ca3af"),
        "status":    TuiRoleStyle(border="#555577", body="#aaaacc"),
    },
)


@dataclass(frozen=True, slots=True)
class TuiKeybindings:
    cancel: str = "escape"
    queue_steer: str = "alt+enter"
    toggle_thinking: str = "ctrl+t"
    toggle_tool_results: str = "ctrl+o"
    session_picker: str = "ctrl+r"
    branch_picker: str = "ctrl+b"
    quit: str = "ctrl+d"
    accept_completion: str = "tab"
    completion_next: str = "down"
    completion_previous: str = "up"
