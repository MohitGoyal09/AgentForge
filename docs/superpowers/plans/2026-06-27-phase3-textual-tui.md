# Phase 3: Textual TUI Replacement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Rich print-renderer (`agentforge_harness/ui/tui.py`) with a full Textual interactive terminal app, retaining the Rich renderer as a `--plain` fallback at `agentforge_harness/ui/plain.py`.

**Architecture:** A thin display layer receives typed `AgentEvent` objects via a `TuiEventAdapter` that mutates a pure `TuiState` dataclass; the Textual `App` subclass drives widget updates from that state. All command dispatch goes exclusively through `get_registry().dispatch(name, argument, ctx) → CommandResult` — zero business logic in TUI files. The `--plain` flag keeps the Rich renderer alive for headless/pipe use.

**Tech Stack:** Python 3.11+, textual>=1.0, rich (retained for plain fallback), pytest, pytest-asyncio.

## Global Constraints

- `from __future__ import annotations` in every new file
- `textual>=1.0` added to `pyproject.toml` project dependencies — no other new top-level deps
- Zero business logic in TUI layer — all commands go through `get_registry().dispatch()`
- Events consumed only via typed `AgentEvent` subclasses from `agent/events.py`
- `--plain` / `--no-tui` flag falls back to the Rich renderer (no feature regressions)
- Current `ui/tui.py` renamed to `ui/plain.py`; new `ui/tui.py` = Textual app
- Do NOT name any external reference project in commits or PR text
- Run `python -m pytest tests/ -x -q` before every commit; keep master green

---

## File Structure

**New files:**
- `agentforge_harness/ui/state.py` — `TuiState` dataclass (display-only: items, buffer, running flag)
- `agentforge_harness/ui/adapter.py` — `TuiEventAdapter` (AgentEvent → TuiState mutations)
- `agentforge_harness/ui/widgets.py` — `TranscriptView`, `TranscriptMessageWidget`, `StreamingMessageWidget`, `SessionSidebar`
- `agentforge_harness/ui/autocomplete.py` — `CompletionItem`, `CompletionState`, `build_completion_state()`
- `agentforge_harness/ui/config.py` — `TuiTheme`, `TuiKeybindings` (frozen dataclasses)
- `agentforge_harness/ui/tui.py` — `AgentForgeTuiApp(App)` (main Textual application)

**Modified files:**
- `agentforge_harness/ui/plain.py` — renamed from current `ui/tui.py` (Rich print-renderer, unchanged)
- `agentforge_harness/cli/commands.py` — add `--plain` flag, route to plain.py or new TUI
- `agentforge_harness/cli/run.py` — wire `--plain` flag through to CLI constructor
- `pyproject.toml` — add `textual>=1.0` dependency

---

### Task 1: Foundation — rename plain.py, add textual dep, --plain flag

**Files:**
- Rename: `agentforge_harness/ui/tui.py` → `agentforge_harness/ui/plain.py`
- Modify: `agentforge_harness/cli/commands.py`
- Modify: `agentforge_harness/cli/run.py` (or wherever CLI entry is)
- Modify: `pyproject.toml`
- Test: `tests/test_plain_renderer.py`

**Interfaces:**
- Produces: `PlainTUI` class in `ui/plain.py` (rename of `TUI` class, or add alias `PlainTUI = TUI`)
- Produces: `--plain` / `--no-tui` CLI flag that selects `PlainTUI` over the Textual app

- [ ] **Step 1: Rename tui.py to plain.py**

```bash
git mv agentforge_harness/ui/tui.py agentforge_harness/ui/plain.py
```

- [ ] **Step 2: Add PlainTUI alias to plain.py**

Open `agentforge_harness/ui/plain.py`. Add at the end of the file:

```python
# Alias for explicit import from the plain renderer path
PlainTUI = TUI
```

Also update any `from agentforge_harness.ui.tui import TUI` imports in the codebase:

```bash
grep -rn "from agentforge_harness.ui.tui import\|from .tui import\|ui.tui" agentforge_harness/ --include="*.py"
```

For each hit, change `from agentforge_harness.ui.tui import TUI` to `from agentforge_harness.ui.plain import TUI`.

- [ ] **Step 3: Add textual to pyproject.toml**

In `pyproject.toml`, find the `[project]` `dependencies` list and add:
```
"textual>=1.0",
```

Install: `pip install textual>=1.0`

- [ ] **Step 4: Add --plain flag to CLI**

In `agentforge_harness/cli/run.py` (or wherever `typer.run` / argparse entry is), add a `--plain` boolean flag:

```python
import typer

app = typer.Typer()

@app.command()
def main(
    plain: bool = typer.Option(False, "--plain", "--no-tui", help="Use plain Rich renderer instead of TUI"),
    # ... existing flags ...
) -> None:
    from agentforge_harness.config.config import Config
    config = Config.from_env()
    if plain:
        from agentforge_harness.cli.commands import CLI
        import asyncio
        cli = CLI(config=config)
        asyncio.run(cli.run_interactive())
    else:
        from agentforge_harness.ui.tui import run_tui
        import asyncio
        asyncio.run(run_tui(config=config))
```

- [ ] **Step 5: Write failing test**

Create `tests/test_plain_renderer.py`:

```python
from __future__ import annotations
import pytest
from agentforge_harness.ui.plain import TUI, PlainTUI


def test_plain_tui_alias():
    """PlainTUI and TUI refer to the same class."""
    assert PlainTUI is TUI


def test_tui_class_has_required_methods():
    """The plain renderer exposes the same interface as before the rename."""
    assert hasattr(TUI, "show_help")
    assert hasattr(TUI, "show_error")
    assert hasattr(TUI, "begin_assistant")
    assert hasattr(TUI, "stream_assistant_delta")
    assert hasattr(TUI, "end_assistant")
    assert hasattr(TUI, "tool_call_start")
    assert hasattr(TUI, "tool_call_complete")
```

- [ ] **Step 6: Run test — must pass**

```bash
python -m pytest tests/test_plain_renderer.py -v
```

Expected: PASS (TUI class already has these methods).

- [ ] **Step 7: Run full suite**

```bash
python -m pytest tests/ -x -q 2>&1 | tail -5
```

Expected: same pass count as before (no regressions from rename).

- [ ] **Step 8: Commit**

```bash
git add agentforge_harness/ui/plain.py agentforge_harness/cli/run.py pyproject.toml tests/test_plain_renderer.py
git add -u  # pick up any imports updated in step 2
git commit -m "feat(tui): rename Rich renderer to plain.py, add --plain flag and textual dep"
```

---

### Task 2: TuiState + TuiEventAdapter

**Files:**
- Create: `agentforge_harness/ui/state.py`
- Create: `agentforge_harness/ui/adapter.py`
- Test: `tests/test_tui_state.py`
- Test: `tests/test_tui_adapter.py`

**Interfaces:**
- Consumes: `AgentEvent` typed subclasses from `agentforge_harness/agent/events.py`
- Produces: `TuiState` — mutable display state consumed by Task 6 (TUI app)
- Produces: `TuiEventAdapter.apply(event)` — the bridge from events to state

- [ ] **Step 1: Write failing tests**

Create `tests/test_tui_state.py`:

```python
from __future__ import annotations
import pytest
from agentforge_harness.ui.state import TuiState, ChatItem, ChatItemRole


def test_initial_state_is_empty():
    state = TuiState()
    assert state.items == []
    assert state.assistant_buffer == ""
    assert state.running is False
    assert state.show_thinking is False
    assert state.show_tool_results is True


def test_add_user_message():
    state = TuiState()
    state.add_user_message("hello")
    assert len(state.items) == 1
    assert state.items[0].role == "user"
    assert state.items[0].text == "hello"


def test_add_assistant_delta_accumulates():
    state = TuiState()
    state.flush_assistant_delta("hello ")
    state.flush_assistant_delta("world")
    items = [i for i in state.items if i.role == "assistant"]
    assert len(items) == 1
    assert items[0].text == "hello world"


def test_clear_resets_state():
    state = TuiState()
    state.add_user_message("hi")
    state.running = True
    state.clear()
    assert state.items == []
    assert state.running is False


def test_toggle_thinking():
    state = TuiState()
    assert state.show_thinking is False
    state.toggle_thinking()
    assert state.show_thinking is True


def test_toggle_tool_results():
    state = TuiState()
    assert state.show_tool_results is True
    state.toggle_tool_results()
    assert state.show_tool_results is False
```

- [ ] **Step 2: Run test — must FAIL**

```bash
python -m pytest tests/test_tui_state.py -v 2>&1 | head -20
```

Expected: FAIL (module not found).

- [ ] **Step 3: Implement state.py**

Create `agentforge_harness/ui/state.py`:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

ChatItemRole = Literal["user", "assistant", "tool", "error", "status", "thinking"]


@dataclass
class ChatItem:
    role: ChatItemRole
    text: str
    tool_call_id: str = ""
    always_show: bool = False


@dataclass
class TuiState:
    items: list[ChatItem] = field(default_factory=list)
    assistant_buffer: str = ""
    thinking_buffer: str = ""
    running: bool = False
    show_thinking: bool = False
    show_tool_results: bool = True

    def add_user_message(self, text: str) -> None:
        self.items.append(ChatItem(role="user", text=text))

    def flush_assistant_delta(self, delta: str) -> None:
        self.assistant_buffer += delta
        existing = [i for i in self.items if i.role == "assistant"]
        if existing:
            existing[-1].text = self.assistant_buffer
        else:
            self.items.append(ChatItem(role="assistant", text=self.assistant_buffer))

    def finalize_assistant(self) -> None:
        self.assistant_buffer = ""

    def flush_thinking_delta(self, delta: str) -> None:
        self.thinking_buffer += delta
        existing = [i for i in self.items if i.role == "thinking"]
        if existing:
            existing[-1].text = self.thinking_buffer
        else:
            self.items.append(ChatItem(role="thinking", text=self.thinking_buffer))

    def finalize_thinking(self) -> None:
        self.thinking_buffer = ""

    def add_tool_item(self, call_id: str, name: str, args: dict) -> None:
        import json
        text = f"[{name}] {json.dumps(args, ensure_ascii=False)[:200]}"
        self.items.append(ChatItem(role="tool", text=text, tool_call_id=call_id))

    def update_tool_result(self, call_id: str, output: str, success: bool) -> None:
        for item in reversed(self.items):
            if item.role == "tool" and item.tool_call_id == call_id:
                status = "✓" if success else "✗"
                item.text = item.text.split("\n")[0] + f"\n{status} {output[:300]}"
                return

    def add_error(self, text: str) -> None:
        self.items.append(ChatItem(role="error", text=text))

    def add_status(self, text: str) -> None:
        self.items.append(ChatItem(role="status", text=text))

    def toggle_thinking(self) -> None:
        self.show_thinking = not self.show_thinking

    def toggle_tool_results(self) -> None:
        self.show_tool_results = not self.show_tool_results

    def clear(self) -> None:
        self.items.clear()
        self.assistant_buffer = ""
        self.thinking_buffer = ""
        self.running = False
```

- [ ] **Step 4: Write failing adapter test**

Create `tests/test_tui_adapter.py`:

```python
from __future__ import annotations
import pytest
from unittest.mock import MagicMock
from agentforge_harness.ui.state import TuiState
from agentforge_harness.ui.adapter import TuiEventAdapter
from agentforge_harness.agent.events import AgentEventType


def _make_event(event_type, data=None):
    evt = MagicMock()
    evt.type = event_type
    evt.data = data or {}
    return evt


def test_agents_start_sets_running():
    state = TuiState()
    adapter = TuiEventAdapter(state)
    adapter.apply(_make_event(AgentEventType.AGENTS_START))
    assert state.running is True


def test_agents_end_clears_running():
    state = TuiState()
    state.running = True
    adapter = TuiEventAdapter(state)
    adapter.apply(_make_event(AgentEventType.AGENTS_END, {"content": "done"}))
    assert state.running is False


def test_text_delta_appends_to_buffer():
    state = TuiState()
    adapter = TuiEventAdapter(state)
    adapter.apply(_make_event(AgentEventType.AGENTS_START))
    adapter.apply(_make_event(AgentEventType.TEXT_DELTA, {"content": "hello"}))
    adapter.apply(_make_event(AgentEventType.TEXT_DELTA, {"content": " world"}))
    items = [i for i in state.items if i.role == "assistant"]
    assert items[0].text == "hello world"


def test_agent_error_adds_error_item():
    state = TuiState()
    adapter = TuiEventAdapter(state)
    adapter.apply(_make_event(AgentEventType.AGENT_ERROR, {"error": "boom"}))
    errors = [i for i in state.items if i.role == "error"]
    assert len(errors) == 1
    assert "boom" in errors[0].text
```

- [ ] **Step 5: Implement adapter.py**

Create `agentforge_harness/ui/adapter.py`:

```python
from __future__ import annotations
from agentforge_harness.ui.state import TuiState
from agentforge_harness.agent.events import AgentEventType


class TuiEventAdapter:
    """Translates AgentEvent objects into TuiState mutations."""

    def __init__(self, state: TuiState) -> None:
        self._state = state

    def apply(self, event) -> None:
        t = event.type
        d = event.data or {}

        if t == AgentEventType.AGENTS_START:
            self._state.running = True

        elif t == AgentEventType.AGENTS_END:
            self._state.running = False
            self._state.finalize_assistant()
            self._state.finalize_thinking()

        elif t == AgentEventType.TEXT_DELTA:
            self._state.flush_assistant_delta(d.get("content", ""))

        elif t == AgentEventType.TEXT_COMPLETE:
            self._state.finalize_assistant()

        elif t == AgentEventType.THINKING_DELTA:
            self._state.flush_thinking_delta(d.get("content", ""))

        elif t == AgentEventType.TOOL_CALL_START:
            self._state.add_tool_item(
                call_id=d.get("call_id", ""),
                name=d.get("name", "unknown"),
                args=d.get("arguments", {}),
            )

        elif t == AgentEventType.TOOL_CALL_COMPLETE:
            self._state.update_tool_result(
                call_id=d.get("call_id", ""),
                output=str(d.get("output", "")),
                success=d.get("success", False),
            )

        elif t == AgentEventType.AGENT_ERROR:
            self._state.running = False
            self._state.add_error(d.get("error", "Unknown error"))
```

- [ ] **Step 6: Run tests — must pass**

```bash
python -m pytest tests/test_tui_state.py tests/test_tui_adapter.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add agentforge_harness/ui/state.py agentforge_harness/ui/adapter.py tests/test_tui_state.py tests/test_tui_adapter.py
git commit -m "feat(tui): add TuiState dataclass and TuiEventAdapter"
```

---

### Task 3: TuiTheme + TuiKeybindings config

**Files:**
- Create: `agentforge_harness/ui/config.py`
- Test: `tests/test_tui_config.py`

**Interfaces:**
- Produces: `TuiTheme` frozen dataclass with role colors, used by Tasks 4 and 6
- Produces: `TuiKeybindings` frozen dataclass, used by Task 6

- [ ] **Step 1: Write failing test**

Create `tests/test_tui_config.py`:

```python
from __future__ import annotations
import pytest
from agentforge_harness.ui.config import TuiTheme, TuiKeybindings, DEFAULT_THEME


def test_default_theme_is_frozen():
    with pytest.raises((AttributeError, TypeError)):
        DEFAULT_THEME.screen_background = "red"


def test_theme_has_role_styles():
    assert "user" in DEFAULT_THEME.role_styles
    assert "assistant" in DEFAULT_THEME.role_styles
    assert "tool" in DEFAULT_THEME.role_styles
    assert "error" in DEFAULT_THEME.role_styles
    assert "thinking" in DEFAULT_THEME.role_styles


def test_default_keybindings():
    kb = TuiKeybindings()
    assert kb.cancel == "escape"
    assert kb.queue_steer == "alt+enter"
    assert kb.toggle_thinking == "ctrl+t"
    assert kb.toggle_tool_results == "ctrl+o"
    assert kb.session_picker == "ctrl+r"
```

- [ ] **Step 2: Run test — must FAIL**

```bash
python -m pytest tests/test_tui_config.py -v 2>&1 | head -10
```

- [ ] **Step 3: Implement config.py**

Create `agentforge_harness/ui/config.py`:

```python
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
```

- [ ] **Step 4: Run test — must pass**

```bash
python -m pytest tests/test_tui_config.py -v
```

- [ ] **Step 5: Commit**

```bash
git add agentforge_harness/ui/config.py tests/test_tui_config.py
git commit -m "feat(tui): add TuiTheme and TuiKeybindings config dataclasses"
```

---

### Task 4: Autocomplete engine

**Files:**
- Create: `agentforge_harness/ui/autocomplete.py`
- Test: `tests/test_tui_autocomplete.py`

**Interfaces:**
- Consumes: command names from `get_registry().known_commands` (list of str)
- Produces: `CompletionState` with `CompletionItem` list; `build_completion_state(text, *, commands, cwd)` factory

- [ ] **Step 1: Write failing tests**

Create `tests/test_tui_autocomplete.py`:

```python
from __future__ import annotations
import pytest
from pathlib import Path
from agentforge_harness.ui.autocomplete import (
    build_completion_state,
    CompletionState,
    CompletionItem,
)


def test_slash_prefix_suggests_commands():
    state = build_completion_state("/he", commands=["/help", "/history", "/exit"])
    assert len(state.items) >= 1
    names = [i.replacement for i in state.items]
    assert "/help" in names


def test_no_prefix_returns_empty():
    state = build_completion_state("hello world", commands=["/help"])
    assert state.items == []


def test_exact_slash_shows_all_commands():
    commands = ["/help", "/exit", "/stats"]
    state = build_completion_state("/", commands=commands)
    replacements = [i.replacement for i in state.items]
    for cmd in commands:
        assert cmd in replacements


def test_select_next_wraps():
    state = CompletionState(items=[
        CompletionItem(display="/help", replacement="/help", start=0, end=1),
        CompletionItem(display="/history", replacement="/history", start=0, end=1),
    ])
    assert state.selected_index == 0
    state2 = state.select_next()
    assert state2.selected_index == 1
    state3 = state2.select_next()
    assert state3.selected_index == 0  # wraps


def test_apply_replaces_text():
    item = CompletionItem(display="/help", replacement="/help", start=0, end=3)
    result = item.apply("/he")
    assert result == "/help"
```

- [ ] **Step 2: Run test — must FAIL**

```bash
python -m pytest tests/test_tui_autocomplete.py -v 2>&1 | head -15
```

- [ ] **Step 3: Implement autocomplete.py**

Create `agentforge_harness/ui/autocomplete.py`:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CompletionItem:
    display: str
    replacement: str
    start: int
    end: int
    description: str = ""

    def apply(self, text: str) -> str:
        return f"{text[:self.start]}{self.replacement}{text[self.end:]}"


@dataclass(frozen=True, slots=True)
class CompletionState:
    items: tuple[CompletionItem, ...] = ()
    selected_index: int = 0

    @property
    def selected(self) -> CompletionItem | None:
        if not self.items:
            return None
        return self.items[self.selected_index]

    def select_next(self) -> CompletionState:
        if not self.items:
            return self
        return CompletionState(
            items=self.items,
            selected_index=(self.selected_index + 1) % len(self.items),
        )

    def select_previous(self) -> CompletionState:
        if not self.items:
            return self
        return CompletionState(
            items=self.items,
            selected_index=(self.selected_index - 1) % len(self.items),
        )


def build_completion_state(
    text: str,
    *,
    commands: list[str],
    cwd: Path | None = None,
) -> CompletionState:
    """Build completion suggestions for the current prompt text."""
    if not text.startswith("/"):
        return CompletionState()

    # Find slash commands matching the prefix
    prefix = text.lower()
    matched = [
        CompletionItem(
            display=cmd,
            replacement=cmd,
            start=0,
            end=len(text),
        )
        for cmd in sorted(commands)
        if cmd.lower().startswith(prefix)
    ]
    return CompletionState(items=tuple(matched))
```

- [ ] **Step 4: Run tests — must pass**

```bash
python -m pytest tests/test_tui_autocomplete.py -v
```

- [ ] **Step 5: Commit**

```bash
git add agentforge_harness/ui/autocomplete.py tests/test_tui_autocomplete.py
git commit -m "feat(tui): add autocomplete engine for slash-command completion"
```

---

### Task 5: Textual Widgets — TranscriptView, SessionSidebar

**Files:**
- Create: `agentforge_harness/ui/widgets.py`
- Test: `tests/test_tui_widgets.py`

**Interfaces:**
- Consumes: `TuiState` from `ui/state.py`, `TuiTheme` from `ui/config.py`
- Produces: `TranscriptView`, `TranscriptMessageWidget`, `SessionSidebar` — Textual widget classes

- [ ] **Step 1: Write failing tests**

Create `tests/test_tui_widgets.py`:

```python
from __future__ import annotations
import pytest
from agentforge_harness.ui.state import TuiState, ChatItem
from agentforge_harness.ui.config import DEFAULT_THEME
from agentforge_harness.ui.widgets import (
    TranscriptView,
    SessionSidebar,
    _format_role_label,
    _item_to_markup,
)


def test_format_role_label_user():
    label = _format_role_label("user", DEFAULT_THEME)
    assert "user" in label.lower() or "▌" in label


def test_item_to_markup_assistant():
    item = ChatItem(role="assistant", text="hello world")
    markup = _item_to_markup(item, DEFAULT_THEME, show_tool_results=True)
    assert "hello world" in markup


def test_item_to_markup_error():
    item = ChatItem(role="error", text="something broke")
    markup = _item_to_markup(item, DEFAULT_THEME, show_tool_results=True)
    assert "something broke" in markup


def test_item_to_markup_thinking_hidden():
    item = ChatItem(role="thinking", text="internal reasoning")
    markup = _item_to_markup(item, DEFAULT_THEME, show_tool_results=True, show_thinking=False)
    assert "internal reasoning" not in markup
    assert "[thinking hidden]" in markup or markup == ""


def test_transcript_view_is_textual_widget():
    from textual.widget import Widget
    assert issubclass(TranscriptView, Widget)


def test_session_sidebar_is_textual_widget():
    from textual.widget import Widget
    assert issubclass(SessionSidebar, Widget)
```

- [ ] **Step 2: Run test — must FAIL**

```bash
python -m pytest tests/test_tui_widgets.py -v 2>&1 | head -20
```

- [ ] **Step 3: Implement widgets.py**

Create `agentforge_harness/ui/widgets.py`:

```python
from __future__ import annotations
from typing import TYPE_CHECKING
from textual.widget import Widget
from textual.widgets import Static
from textual.scroll_view import ScrollView
from textual.app import ComposeResult
from agentforge_harness.ui.state import TuiState, ChatItem, ChatItemRole
from agentforge_harness.ui.config import TuiTheme, DEFAULT_THEME

if TYPE_CHECKING:
    pass


def _format_role_label(role: ChatItemRole, theme: TuiTheme) -> str:
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
    # Escape Rich markup in user content
    safe_text = item.text.replace("[", "\\[")
    return f"[{color}]{safe_text}[/{color}]"


class TranscriptMessageWidget(Static):
    """A single rendered transcript message."""

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
        label = _format_role_label(item.role, theme)
        body = _item_to_markup(item, theme, show_tool_results=show_tool_results, show_thinking=show_thinking)
        content = f"{label}\n{body}" if body else label
        super().__init__(content, **kwargs)

    def update_item(self, item: ChatItem) -> None:
        self._item = item
        label = _format_role_label(item.role, self._theme)
        body = _item_to_markup(
            item,
            self._theme,
            show_tool_results=self._show_tool_results,
            show_thinking=self._show_thinking,
        )
        self.update(f"{label}\n{body}" if body else label)


class TranscriptView(Widget):
    """Scrollable transcript panel with lazy-mounted message widgets."""

    DEFAULT_CSS = """
    TranscriptView {
        height: 1fr;
        overflow-y: scroll;
        padding: 0 1;
    }
    TranscriptMessageWidget {
        margin-bottom: 1;
    }
    """

    def __init__(self, state: TuiState, theme: TuiTheme = DEFAULT_THEME, **kwargs) -> None:
        self._state = state
        self._theme = theme
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        for item in self._state.items:
            if item.role == "thinking" and not self._state.show_thinking:
                yield TranscriptMessageWidget(
                    item,
                    theme=self._theme,
                    show_thinking=False,
                )
            else:
                yield TranscriptMessageWidget(
                    item,
                    theme=self._theme,
                    show_tool_results=self._state.show_tool_results,
                    show_thinking=self._state.show_thinking,
                )

    def refresh_from_state(self) -> None:
        """Full redraw — call after state mutations."""
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
        """Efficiently append streamed text to the last assistant widget."""
        assistant_widgets = [
            w for w in self.children
            if isinstance(w, TranscriptMessageWidget) and w._item.role == "assistant"
        ]
        if assistant_widgets:
            last = assistant_widgets[-1]
            last.update_item(last._item)
        self.scroll_end(animate=False)


class SessionSidebar(Static):
    """Left sidebar showing session metadata."""

    DEFAULT_CSS = """
    SessionSidebar {
        width: 28;
        padding: 1;
        border-right: solid #333355;
    }
    """

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
        content = (
            f"[{accent}]◆ {mode.upper()}[/{accent}]\n"
            f"model: {model}\n"
            f"turn:  #{turn}\n"
            f"in:    {prompt_tokens:,}\n"
            f"out:   {completion_tokens:,}"
        )
        self.update(content)
```

- [ ] **Step 4: Run tests — must pass**

```bash
python -m pytest tests/test_tui_widgets.py -v
```

- [ ] **Step 5: Commit**

```bash
git add agentforge_harness/ui/widgets.py tests/test_tui_widgets.py
git commit -m "feat(tui): add TranscriptView, TranscriptMessageWidget and SessionSidebar widgets"
```

---

### Task 6: Main TUI App — AgentForgeTuiApp

**Files:**
- Create: `agentforge_harness/ui/tui.py`
- Test: `tests/test_tui_app.py`

**Interfaces:**
- Consumes: All of Tasks 2–5 (state, adapter, config, widgets, autocomplete)
- Consumes: `get_registry().dispatch()` → `CommandResult` from `cli/command_registry.py`
- Consumes: `Agent` from `agent/agent.py` (for async event iteration)
- Produces: `AgentForgeTuiApp(App)` + `run_tui(config)` entry point

- [ ] **Step 1: Write failing tests**

Create `tests/test_tui_app.py`:

```python
from __future__ import annotations
import pytest
from agentforge_harness.ui.tui import AgentForgeTuiApp, run_tui


def test_run_tui_is_callable():
    """run_tui must exist and be importable."""
    import inspect
    assert inspect.iscoroutinefunction(run_tui)


def test_app_class_exists():
    from textual.app import App
    assert issubclass(AgentForgeTuiApp, App)


def test_app_has_required_bindings():
    """Key bindings include quit and toggle_thinking."""
    binding_keys = [b.key for b in AgentForgeTuiApp.BINDINGS]
    assert "ctrl+d" in binding_keys
    assert "ctrl+t" in binding_keys
    assert "ctrl+o" in binding_keys
```

- [ ] **Step 2: Run test — must FAIL**

```bash
python -m pytest tests/test_tui_app.py -v 2>&1 | head -15
```

- [ ] **Step 3: Implement tui.py**

Create `agentforge_harness/ui/tui.py`:

```python
from __future__ import annotations
import asyncio
from typing import Any
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Input, Footer, Header, Static
from textual.containers import Horizontal, Vertical
from agentforge_harness.ui.state import TuiState
from agentforge_harness.ui.adapter import TuiEventAdapter
from agentforge_harness.ui.config import DEFAULT_THEME, TuiTheme, TuiKeybindings
from agentforge_harness.ui.widgets import TranscriptView, SessionSidebar
from agentforge_harness.ui.autocomplete import build_completion_state, CompletionState
from agentforge_harness.agent.agent import Agent
from agentforge_harness.agent.events import AgentEventType
from agentforge_harness.cli.command_registry import CommandContext, get_registry
from agentforge_harness.config.config import Config

_SIDEBAR_MIN_WIDTH = 96


class PromptInput(Input):
    """Single-line prompt input with slash-command awareness."""

    def __init__(self, **kwargs) -> None:
        super().__init__(placeholder="Type a message or /command...", **kwargs)


class AgentForgeTuiApp(App):
    """Full Textual TUI for AgentForge."""

    CSS = """
    Screen {
        background: #1a1a2e;
    }
    #workspace {
        height: 1fr;
    }
    #sidebar {
        width: 28;
        border-right: solid #333355;
        padding: 1;
    }
    #main-pane {
        height: 1fr;
    }
    #transcript {
        height: 1fr;
    }
    #prompt-row {
        height: auto;
        border-top: solid #333355;
        padding: 0 1;
    }
    #prompt-prefix {
        width: 3;
        padding-top: 1;
        color: #4ec9b0;
    }
    #prompt {
        height: auto;
        border: none;
        background: transparent;
    }
    #autocomplete {
        height: auto;
        max-height: 10;
        background: #222244;
        border: solid #444466;
    }
    AgentForgeTuiApp.-hide-sidebar #sidebar {
        display: none;
    }
    """

    BINDINGS = [
        Binding("ctrl+d", "quit", "Quit"),
        Binding("ctrl+t", "toggle_thinking", "Thinking"),
        Binding("ctrl+o", "toggle_tool_results", "Tools"),
        Binding("ctrl+r", "session_picker", "Sessions"),
        Binding("escape", "cancel_run", "Cancel"),
    ]

    def __init__(self, config: Config, **kwargs) -> None:
        super().__init__(**kwargs)
        self.config = config
        self.state = TuiState()
        self.theme = DEFAULT_THEME
        self.keybindings = TuiKeybindings()
        self._agent: Agent | None = None
        self._run_task: asyncio.Task | None = None
        self._completion_state = CompletionState()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="workspace"):
            yield SessionSidebar(id="sidebar")
            with Vertical(id="main-pane"):
                yield TranscriptView(self.state, self.theme, id="transcript")
                with Horizontal(id="prompt-row"):
                    yield Static("❯", id="prompt-prefix")
                    yield PromptInput(id="prompt")
                yield Static("", id="autocomplete")
        yield Footer()

    async def on_mount(self) -> None:
        self._agent = Agent(config=self.config)
        await self._agent.__aenter__()
        self.query_one("#prompt", PromptInput).focus()
        self._update_sidebar()
        self._update_responsive()

    async def on_unmount(self) -> None:
        if self._agent:
            await self._agent.__aexit__(None, None, None)

    def on_resize(self) -> None:
        self._update_responsive()

    def _update_responsive(self) -> None:
        self.set_class(self.size.width < _SIDEBAR_MIN_WIDTH, "-hide-sidebar")

    def _update_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar", SessionSidebar)
        if self._agent and self._agent.session:
            s = self._agent.session
            try:
                usage = s.context_manager.get_total_usage() if s.context_manager else None
            except Exception:
                usage = None
            sidebar.update_from_info(
                mode=s.mode.value if s.mode else "build",
                model=self.config.model_name,
                turn=s._turn_count if hasattr(s, "_turn_count") else 0,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                theme=self.theme,
            )

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """User pressed Enter in the prompt."""
        text = event.value.strip()
        event.input.clear()
        if not text:
            return

        # Clear autocomplete
        self._completion_state = CompletionState()
        self.query_one("#autocomplete", Static).update("")

        if text.startswith("/"):
            await self._handle_command(text)
        else:
            if self.state.running:
                # Inject as steer while running
                await self._queue_message(text, mode="steer")
            else:
                await self._run_prompt(text)

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Update autocomplete as user types."""
        text = event.value
        if not text.startswith("/"):
            self._completion_state = CompletionState()
            self.query_one("#autocomplete", Static).update("")
            return

        commands = list(get_registry().known_commands)
        self._completion_state = build_completion_state(text, commands=commands)
        if self._completion_state.items:
            items_text = "  ".join(i.display for i in self._completion_state.items[:8])
            self.query_one("#autocomplete", Static).update(f"[dim]{items_text}[/dim]")
        else:
            self.query_one("#autocomplete", Static).update("")

    async def on_key(self, event) -> None:
        """Handle special keys for steering and autocomplete."""
        if event.key == "alt+enter":
            event.stop()
            prompt = self.query_one("#prompt", PromptInput)
            text = prompt.value.strip()
            if text and self.state.running:
                prompt.clear()
                await self._queue_message(text, mode="steer")

        elif event.key == "tab" and self._completion_state.selected:
            event.stop()
            prompt = self.query_one("#prompt", PromptInput)
            item = self._completion_state.selected
            prompt.value = item.apply(prompt.value)
            prompt.cursor_position = len(prompt.value)
            self._completion_state = CompletionState()
            self.query_one("#autocomplete", Static).update("")

    async def _handle_command(self, text: str) -> None:
        parts = text.split(maxsplit=1)
        name = parts[0].lower()
        argument = parts[1].strip() if len(parts) > 1 else ""
        ctx = CommandContext(
            session=self._agent.session if self._agent else None,
            config=self.config,
            agent=self._agent,
            last_user_message="",
        )
        result = await get_registry().dispatch(name, argument, ctx)
        if result.exit:
            await self.action_quit()
            return
        if result.error:
            self.state.add_error(result.error)
        elif result.notice:
            self.state.add_status(result.notice)
        self._refresh_transcript()

    async def _run_prompt(self, message: str) -> None:
        if not self._agent:
            return
        self.state.add_user_message(message)
        self._refresh_transcript()
        adapter = TuiEventAdapter(self.state)

        async def _stream():
            async for event in self._agent.run(message):
                adapter.apply(event)
                transcript = self.query_one("#transcript", TranscriptView)
                if event.type == AgentEventType.TEXT_DELTA:
                    transcript.append_delta(event.data.get("content", ""))
                else:
                    transcript.refresh_from_state()
                self._update_sidebar()

        self._run_task = asyncio.create_task(_stream())
        try:
            await self._run_task
        except asyncio.CancelledError:
            pass
        finally:
            self.state.running = False
            self._run_task = None
            self._refresh_transcript()

    async def _queue_message(self, text: str, mode: str = "follow_up") -> None:
        if self._agent and self._agent.session:
            self._agent.session.prompt(text, mode=mode)
            self.state.add_status(f"[queued {mode}]: {text[:60]}")
            self._refresh_transcript()

    def _refresh_transcript(self) -> None:
        try:
            self.query_one("#transcript", TranscriptView).refresh_from_state()
        except Exception:
            pass

    def action_toggle_thinking(self) -> None:
        self.state.toggle_thinking()
        self._refresh_transcript()

    def action_toggle_tool_results(self) -> None:
        self.state.toggle_tool_results()
        self._refresh_transcript()

    def action_cancel_run(self) -> None:
        if self._run_task and not self._run_task.done():
            self._run_task.cancel()
            if self._agent and self._agent.session:
                self._agent.session.request_cancel()

    def action_session_picker(self) -> None:
        self.state.add_status("Session picker: use /new or /resume <id>")
        self._refresh_transcript()

    async def action_quit(self) -> None:
        self.action_cancel_run()
        self.exit()


async def run_tui(config: Config) -> None:
    """Entry point: run the Textual TUI."""
    app = AgentForgeTuiApp(config=config)
    await app.run_async()
```

- [ ] **Step 4: Run tests — must pass**

```bash
python -m pytest tests/test_tui_app.py -v
```

- [ ] **Step 5: Commit**

```bash
git add agentforge_harness/ui/tui.py tests/test_tui_app.py
git commit -m "feat(tui): add AgentForgeTuiApp main Textual application"
```

---

### Task 7: Integration wiring + smoke test

**Files:**
- Modify: `agentforge_harness/cli/run.py` — wire `--plain` flag to select renderer
- Modify: `agentforge_harness/ui/__init__.py` — export `run_tui` and `PlainTUI`
- Test: `tests/test_tui_integration.py`

**Interfaces:**
- Consumes: `run_tui` from `ui/tui.py`, `CLI` from `cli/commands.py`
- Produces: `--plain` flag selects plain renderer; default selects Textual TUI

- [ ] **Step 1: Write failing integration test**

Create `tests/test_tui_integration.py`:

```python
from __future__ import annotations
import pytest
from agentforge_harness.ui import run_tui
from agentforge_harness.ui.plain import TUI as PlainTUI
from agentforge_harness.ui.tui import AgentForgeTuiApp
from agentforge_harness.ui.state import TuiState
from agentforge_harness.ui.adapter import TuiEventAdapter
from agentforge_harness.ui.config import DEFAULT_THEME
from agentforge_harness.ui.autocomplete import build_completion_state
from unittest.mock import MagicMock
from agentforge_harness.agent.events import AgentEventType


def test_ui_package_exports():
    """run_tui is importable from the ui package."""
    import inspect
    assert inspect.iscoroutinefunction(run_tui)


def test_plain_tui_still_works():
    """PlainTUI is importable and has the same interface as before."""
    assert hasattr(PlainTUI, "show_error")
    assert hasattr(PlainTUI, "show_help")


def test_event_pipeline_end_to_end():
    """Events flow: AGENTS_START → TEXT_DELTA → AGENTS_END → state updated."""
    state = TuiState()
    adapter = TuiEventAdapter(state)

    def evt(t, data=None):
        m = MagicMock()
        m.type = t
        m.data = data or {}
        return m

    adapter.apply(evt(AgentEventType.AGENTS_START))
    assert state.running is True

    adapter.apply(evt(AgentEventType.TEXT_DELTA, {"content": "hello "}))
    adapter.apply(evt(AgentEventType.TEXT_DELTA, {"content": "world"}))

    adapter.apply(evt(AgentEventType.AGENTS_END, {"content": "hello world"}))
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
    """Every role in TuiState has a theme entry."""
    roles = ["user", "assistant", "tool", "error", "thinking", "status"]
    for role in roles:
        assert role in DEFAULT_THEME.role_styles, f"Missing theme for role: {role}"
```

- [ ] **Step 2: Update ui/__init__.py**

Edit `agentforge_harness/ui/__init__.py` to expose:

```python
from agentforge_harness.ui.tui import run_tui, AgentForgeTuiApp
from agentforge_harness.ui.plain import TUI as PlainTUI

__all__ = ["run_tui", "AgentForgeTuiApp", "PlainTUI"]
```

- [ ] **Step 3: Wire --plain in run.py**

In `agentforge_harness/cli/run.py`, update the entry-point function so `--plain` selects the plain renderer:

```python
import typer
import asyncio

app_cli = typer.Typer(add_completion=False)

@app_cli.command()
def main(
    plain: bool = typer.Option(False, "--plain", "--no-tui", help="Use plain Rich renderer"),
    message: str = typer.Argument(None, help="Single message (non-interactive)"),
) -> None:
    from agentforge_harness.config.loader import load_config
    config = load_config()
    if plain or message:
        from agentforge_harness.cli.commands import CLI
        cli = CLI(config=config)
        if message:
            asyncio.run(cli.run_single(message))
        else:
            asyncio.run(cli.run_interactive())
    else:
        from agentforge_harness.ui.tui import run_tui
        asyncio.run(run_tui(config=config))
```

(Read the actual run.py first and match its import patterns before applying this.)

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/ -x -q 2>&1 | tail -10
```

Expected: all tests pass including the new integration suite.

- [ ] **Step 5: Verify textual imports work**

```bash
python -c "from agentforge_harness.ui.tui import AgentForgeTuiApp; print('OK')"
python -c "from agentforge_harness.ui.plain import TUI; print('OK')"
python -c "from agentforge_harness.ui import run_tui; print('OK')"
```

- [ ] **Step 6: Commit**

```bash
git add agentforge_harness/ui/__init__.py agentforge_harness/cli/run.py tests/test_tui_integration.py
git commit -m "feat(tui): wire --plain flag and expose run_tui from ui package"
```

---

## GSTACK REVIEW REPORT

| Run | Reviewer | Status | Findings | Verdict |
|-----|----------|--------|----------|---------|
| — | — | NO REVIEWS YET — run `/autoplan` | — | — |
