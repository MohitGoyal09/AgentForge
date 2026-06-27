from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Static

from agentforge_harness.ui.config import DEFAULT_THEME, TuiTheme
from agentforge_harness.ui.state import ChatItem, TuiState


# ---------------------------------------------------------------------------
# Module-level helper functions
# ---------------------------------------------------------------------------


def _format_role_label(role: str, theme: TuiTheme) -> str:
    style = theme.role_styles.get(role)
    color = style.border if style else "#888888"
    labels = {
        "user": "you",
        "assistant": "agent",
        "tool": "tool",
        "error": "error",
        "thinking": "thinking",
        "status": "info",
    }
    label = labels.get(role, role)
    return f"[{color}]▌ {label}[/{color}]"


def _item_to_markup(
    item: ChatItem,
    theme: TuiTheme,
    *,
    show_tool_results: bool = True,
    show_thinking: bool = True,
) -> str:
    if item.role == "thinking" and not show_thinking:
        return "[dim][ thinking hidden — Ctrl+T to show ][/dim]"
    style = theme.role_styles.get(item.role)
    color = style.body if style else "#cccccc"
    safe_text = item.text.replace("[", "\\[")
    return f"[{color}]{safe_text}[/{color}]"


# ---------------------------------------------------------------------------
# TranscriptMessageWidget
# ---------------------------------------------------------------------------


class TranscriptMessageWidget(Static):
    """Renders a single ChatItem as a labelled message block."""

    def __init__(
        self,
        item: ChatItem,
        theme: TuiTheme = DEFAULT_THEME,
        show_tool_results: bool = True,
        show_thinking: bool = True,
        **kwargs,
    ) -> None:
        self._item = item
        self._theme = theme
        self._show_tool_results = show_tool_results
        self._show_thinking = show_thinking
        content = self._build_markup(item)
        super().__init__(content, **kwargs)

    def _build_markup(self, item: ChatItem) -> str:
        label = _format_role_label(item.role, self._theme)
        body = _item_to_markup(
            item,
            self._theme,
            show_tool_results=self._show_tool_results,
            show_thinking=self._show_thinking,
        )
        return f"{label}\n{body}"

    def update_item(self, item: ChatItem) -> None:
        self._item = item
        self.update(self._build_markup(item))


# ---------------------------------------------------------------------------
# TranscriptView
# ---------------------------------------------------------------------------


class TranscriptView(VerticalScroll):
    """Scrollable view of all chat transcript items."""

    def __init__(
        self,
        state: TuiState,
        theme: TuiTheme = DEFAULT_THEME,
        **kwargs,
    ) -> None:
        self._state = state
        self._theme = theme
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        for item in self._state.items:
            yield TranscriptMessageWidget(
                item,
                theme=self._theme,
                show_tool_results=self._state.show_tool_results,
                show_thinking=self._state.show_thinking,
            )

    def refresh_from_state(self) -> None:
        self.query("TranscriptMessageWidget").remove()
        for item in self._state.items:
            self.mount(
                TranscriptMessageWidget(
                    item,
                    theme=self._theme,
                    show_tool_results=self._state.show_tool_results,
                    show_thinking=self._state.show_thinking,
                )
            )
        self.scroll_end(animate=False)

    def append_delta(self, delta: str) -> None:
        assistant_widgets = [
            w
            for w in self.children
            if isinstance(w, TranscriptMessageWidget) and w._item.role == "assistant"
        ]
        if assistant_widgets:
            last = assistant_widgets[-1]
            last.update_item(last._item)
        self.scroll_end(animate=False)


# ---------------------------------------------------------------------------
# SessionSidebar
# ---------------------------------------------------------------------------


class SessionSidebar(Static):
    """Sidebar panel showing current session metadata."""

    DEFAULT_CSS = """SessionSidebar {
    width: 26;
    padding: 1 1;
    border-right: solid #1a1a1a;
    background: #050505;
    color: #aaaaaa;
}"""

    def update_from_info(
        self,
        *,
        mode: str,
        model: str,
        turn: int,
        prompt_tokens: int,
        completion_tokens: int,
        theme: TuiTheme = DEFAULT_THEME,
        tools: list[str] | None = None,
        skills: list[str] | None = None,
    ) -> None:
        amber = "#d4a04a"
        dim = "#555566"
        text = "#aaaaaa"

        safe_model = str(model).replace("[", "\\[").replace("]", "\\]")
        safe_mode = str(mode).replace("[", "\\[").replace("]", "\\]")

        lines = [
            f"[bold {amber}]AgentForge[/bold {amber}]",
            "",
            f"[bold {amber}]session[/bold {amber}]",
            f"[{dim}]mode    [/{dim}] [{text}]{safe_mode}[/{text}]",
            f"[{dim}]model   [/{dim}] [{text}]{safe_model}[/{text}]",
            f"[{dim}]turn    [/{dim}] [{text}]{turn}[/{text}]",
            f"[{dim}]in      [/{dim}] [{text}]{prompt_tokens:,}[/{text}]",
            f"[{dim}]out     [/{dim}] [{text}]{completion_tokens:,}[/{text}]",
        ]

        if tools:
            lines += ["", f"[bold {amber}]tools[/bold {amber}]"]
            for t in tools[:10]:
                safe_t = str(t).replace("[", "\\[")
                lines.append(f"[{dim}]•[/{dim}] [{text}]{safe_t}[/{text}]")

        if skills:
            lines += ["", f"[bold {amber}]skills[/bold {amber}]"]
            for s in skills[:20]:
                safe_s = str(s).replace("[", "\\[")
                lines.append(f"[{dim}]•[/{dim}] [{text}]{safe_s}[/{text}]")

        self.update("\n".join(lines))


# ---------------------------------------------------------------------------
# StatusBar
# ---------------------------------------------------------------------------


class StatusBar(Static):
    """Single-line status bar at the bottom showing cwd + context info."""

    DEFAULT_CSS = """StatusBar {
    height: 1;
    background: #050505;
    border-top: solid #1a1a1a;
    padding: 0 1;
    color: #555566;
}"""

    def update_status(
        self,
        *,
        cwd: str,
        branch: str,
        prompt_tokens: int,
        max_tokens: int,
        model: str,
        mode: str,
    ) -> None:
        amber = "#d4a04a"
        dim = "#555566"
        left = f"[{dim}]{cwd}[/{dim}] [{amber}]({branch})[/{amber}]"
        ctx = f"{prompt_tokens // 1000}k/{max_tokens // 1000}k context"
        right = f"[{dim}]{ctx}  {model} ({mode})[/{dim}]"
        self.update(f"{left}  {right}")
