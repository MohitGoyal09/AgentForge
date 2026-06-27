from __future__ import annotations

from textual.app import ComposeResult
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
        content = self._render_content(item)
        super().__init__(content, **kwargs)

    def _render_content(self, item: ChatItem) -> str:
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
        self.update(self._render_content(item))


# ---------------------------------------------------------------------------
# TranscriptView
# ---------------------------------------------------------------------------


class TranscriptView(Widget):
    """Scrollable view of all chat transcript items."""

    DEFAULT_CSS = "TranscriptView { height: 1fr; overflow-y: scroll; padding: 0 1; }"

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
        self.remove_children()
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

    DEFAULT_CSS = "SessionSidebar { width: 28; padding: 1; border-right: solid #333355; }"

    def update_from_info(
        self,
        *,
        mode: str,
        model: str,
        turn: int,
        prompt_tokens: int,
        completion_tokens: int,
        theme: TuiTheme = DEFAULT_THEME,
    ) -> None:
        accent = theme.accent
        dim = "#555577"
        lines = [
            f"[{accent}]AgentForge[/{accent}]",
            "",
            f"[{dim}]Mode      [/{dim}] {mode}",
            f"[{dim}]Model     [/{dim}] {model[:20]}",
            f"[{dim}]Turn      [/{dim}] {turn}",
            "",
            f"[{dim}]Prompt    [/{dim}] {prompt_tokens:,}",
            f"[{dim}]Completion[/{dim}] {completion_tokens:,}",
        ]
        self.update("\n".join(lines))
