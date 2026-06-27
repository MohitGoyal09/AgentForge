from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Input, Static

from agentforge_harness.ui.adapter import TuiEventAdapter
from agentforge_harness.ui.autocomplete import build_completion_state
from agentforge_harness.ui.config import DEFAULT_THEME, TuiTheme
from agentforge_harness.ui.state import TuiState
from agentforge_harness.ui.widgets import SessionSidebar, StatusBar, TranscriptView

if TYPE_CHECKING:
    from agentforge_harness.config.config import Config


class AgentForgeTuiApp(App):
    """Full Textual TUI for AgentForge."""

    TITLE = "AgentForge"
    SUB_TITLE = ""

    BINDINGS = [
        Binding("ctrl+d", "quit", "Quit"),
        Binding("ctrl+t", "toggle_thinking", "Thinking"),
        Binding("ctrl+o", "toggle_tool_results", "Tools"),
        Binding("ctrl+r", "session_picker", "Sessions"),
        Binding("escape", "cancel_run", "Cancel"),
    ]

    CSS = """
Screen {
    background: #0d0d0d;
    color: #cccccc;
    layers: base overlay;
}
#layout {
    height: 1fr;
}
#main {
    height: 1fr;
}
#transcript {
    height: 1fr;
    padding: 0 1;
    background: #0d0d0d;
}
#input-row {
    height: auto;
    border-top: solid #1a1a1a;
    padding: 0;
    background: #0d0d0d;
}
#prompt-prefix {
    width: 3;
    padding: 0 0 0 1;
    content-align: center middle;
    color: #d4a04a;
}
#prompt {
    width: 1fr;
    border: none;
    background: transparent;
    color: #cccccc;
    padding: 0 1;
}
Input:focus {
    border: none;
    background: transparent;
}
#autocomplete {
    height: auto;
    padding: 0 4;
    color: #333344;
    background: #0d0d0d;
}
TranscriptMessageWidget {
    padding: 0 0 1 0;
}
Footer {
    background: #050505;
    color: #555566;
}
"""

    def __init__(self, config: Config, theme: TuiTheme = DEFAULT_THEME, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._theme = theme
        self.state = TuiState()
        self._adapter = TuiEventAdapter(self.state)
        self._agent = None
        self._run_task: asyncio.Task | None = None
        self._last_user_message: str = ""

    def compose(self) -> ComposeResult:
        from textual.containers import Horizontal, Vertical

        with Horizontal(id="layout"):
            yield SessionSidebar(id="sidebar")
            with Vertical(id="main"):
                yield TranscriptView(self.state, theme=self._theme, id="transcript")
                yield Static("", id="autocomplete")
                with Horizontal(id="input-row"):
                    yield Static("❯", id="prompt-prefix")
                    yield Input(
                        placeholder="Ask AgentForge… Enter submits, Alt+Enter steers",
                        id="prompt",
                    )
        yield StatusBar(id="statusbar")
        yield Footer()

    async def on_mount(self) -> None:
        from agentforge_harness.agent.agent import Agent

        self._agent = Agent(config=self._config)
        await self._agent.__aenter__()
        self.query_one("#prompt", Input).focus()
        self._update_sidebar()

    async def on_unmount(self) -> None:
        if self._agent is not None:
            try:
                await self._agent.__aexit__(None, None, None)
            except Exception:
                pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""
        self.query_one("#autocomplete", Static).update("")

        if text.startswith("/"):
            self.run_worker(self._handle_command(text), exclusive=False)
        elif self.state.running:
            self._queue_message(text, mode="steer")
        else:
            self._last_user_message = text
            self.run_worker(self._run_prompt(text), exclusive=False)

    def on_input_changed(self, event: Input.Changed) -> None:
        text = event.value
        if not text.startswith("/"):
            self.query_one("#autocomplete", Static).update("")
            return
        registry = self._get_registry()
        commands = [f"/{name}" if not name.startswith("/") else name
                    for name in registry.known_commands]
        completion = build_completion_state(text, commands=commands)
        if completion.items:
            suggestions = "  ".join(item.display for item in completion.items[:8])
            self.query_one("#autocomplete", Static).update(f"[dim]{suggestions}[/dim]")
        else:
            self.query_one("#autocomplete", Static).update("")

    def on_key(self, event) -> None:
        key = event.key
        if key == "alt+enter":
            prompt_widget = self.query_one("#prompt", Input)
            text = prompt_widget.value.strip()
            if text:
                prompt_widget.value = ""
                self._queue_message(text, mode="steer")
        elif key == "tab":
            prompt_widget = self.query_one("#prompt", Input)
            text = prompt_widget.value
            if text.startswith("/"):
                registry = self._get_registry()
                commands = [f"/{name}" if not name.startswith("/") else name
                            for name in registry.known_commands]
                completion = build_completion_state(text, commands=commands)
                if completion.selected:
                    prompt_widget.value = completion.selected.replacement
                    prompt_widget.cursor_position = len(prompt_widget.value)
                    event.prevent_default()

    def _get_registry(self):
        from agentforge_harness.cli.command_registry import get_registry
        return get_registry()

    async def _handle_command(self, text: str) -> None:
        from agentforge_harness.cli.command_registry import CommandContext, get_registry

        parts = text.split(None, 1)
        name = parts[0]
        argument = parts[1] if len(parts) > 1 else ""

        session = self._agent.session if self._agent else None
        ctx = CommandContext(
            session=session,
            config=self._config,
            agent=self._agent,
            last_user_message=self._last_user_message,
        )
        try:
            result = await get_registry().dispatch(name, argument, ctx)
        except Exception as exc:
            self.state.add_error(f"Command error: {exc}")
            self._refresh_transcript()
            return

        if result.exit:
            await self.action_quit()
            return

        if result.clear:
            self.state.clear()
            self._refresh_transcript()

        if result.error:
            self.state.add_error(f"{result.error_title}: {result.error}")
            self._refresh_transcript()

        if result.notice:
            self.state.add_status(result.notice)
            self._refresh_transcript()

        if not result.handled:
            self.state.add_error(f"Unknown command: {name}")
            self._refresh_transcript()

    async def _run_prompt(self, message: str) -> None:
        if self._run_task and not self._run_task.done():
            # Previous run still active — queue as steer instead
            self._queue_message(message, mode="steer")
            return
        if self._agent is None:
            return
        self.state.add_user_message(message)
        self._refresh_transcript()

        async def _stream() -> None:
            try:
                async for event in self._agent.run(message):
                    self._adapter.apply(event)
                    self._refresh_transcript()
            except asyncio.CancelledError:
                self.state.add_status("[Cancelled]")
                self.state.running = False
                self._refresh_transcript()
            except Exception as exc:
                self.state.add_error(f"Run error: {exc}")
                self.state.running = False
                self._refresh_transcript()
            finally:
                self._update_sidebar()
                self._run_task = None

        self._run_task = asyncio.create_task(_stream())

    def _queue_message(self, text: str, mode: str = "follow_up") -> None:
        if self._agent and self._agent.session:
            try:
                self._agent.session.prompt(text, mode)
                self.state.add_status(f"[Queued {mode}] {text[:60]}")
                self._refresh_transcript()
            except Exception as exc:
                self.state.add_error(f"Queue error: {exc}")
                self._refresh_transcript()

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
            try:
                self._agent.session.request_cancel()
            except Exception:
                pass

    async def action_quit(self) -> None:
        self.action_cancel_run()
        self.exit()

    def action_session_picker(self) -> None:
        self.state.add_status(
            "Session picker: use /sessions to list sessions, /resume <id> to restore."
        )
        self._refresh_transcript()

    def _update_sidebar(self) -> None:
        try:
            sidebar = self.query_one("#sidebar", SessionSidebar)
        except Exception:
            return

        session = self._agent.session if self._agent else None
        mode = session.mode.value if session and session.mode else "build"
        model = self._config.model_name
        turn = getattr(session, "_turn_count", 0) if session else 0
        prompt_tokens = 0
        completion_tokens = 0
        max_tokens = 256_000

        if session and session.context_manager is not None:
            try:
                usage = session.context_manager.get_total_usage()
                prompt_tokens = usage.prompt_tokens or 0
                completion_tokens = usage.completion_tokens or 0
            except Exception:
                pass

        # Get tool names
        tools: list[str] = []
        if session:
            try:
                if hasattr(session, "tool_registry") and session.tool_registry:
                    tools = list(session.tool_registry.keys())[:10]
                elif hasattr(session, "_tools") and session._tools:
                    tools = [getattr(t, "name", str(t)) for t in session._tools][:10]
            except Exception:
                pass

        # Get active skill names
        skills: list[str] = []
        if session:
            try:
                if hasattr(session, "skills_manager") and session.skills_manager:
                    sm = session.skills_manager
                    if hasattr(sm, "active_skills"):
                        skills = list(sm.active_skills)[:20]
                    elif hasattr(sm, "_active"):
                        skills = list(sm._active)[:20]
            except Exception:
                pass

        sidebar.update_from_info(
            mode=mode,
            model=model,
            turn=turn,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            theme=self._theme,
            tools=tools or None,
            skills=skills or None,
        )

        # Update status bar
        try:
            import os
            import subprocess

            cwd = os.path.basename(os.getcwd())
            try:
                branch = subprocess.check_output(
                    ["git", "branch", "--show-current"],
                    capture_output=True,
                    text=True,
                    timeout=1,
                ).stdout.strip()
            except Exception:
                branch = "main"
            statusbar = self.query_one("#statusbar", StatusBar)
            statusbar.update_status(
                cwd=f"~/{cwd}",
                branch=branch,
                prompt_tokens=prompt_tokens,
                max_tokens=max_tokens,
                model=model,
                mode=mode,
            )
        except Exception:
            pass

    def _refresh_transcript(self) -> None:
        try:
            transcript = self.query_one("#transcript", TranscriptView)
            transcript.refresh_from_state()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def run_tui(config: Config) -> None:
    """Launch the Textual TUI and run until the user quits."""
    app = AgentForgeTuiApp(config=config)
    await app.run_async()
