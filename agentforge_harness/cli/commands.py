"""CLI — interactive run loop and TUI render layer.

_handle_command dispatches every slash-command through the CommandRegistry
and renders the resulting CommandResult via _render_result.  All business
logic lives in command_registry.py; this file only drives the TUI.
"""
from __future__ import annotations

import asyncio
import difflib
from typing import Any

from agentforge_harness.agent.agent import Agent
from agentforge_harness.agent.events import AgentEventType
from agentforge_harness.agent.modes import AgentMode
from agentforge_harness.cli.command_registry import CommandContext, get_registry
from agentforge_harness.cli.command_result import CommandResult
from agentforge_harness.config.config import Config
from agentforge_harness.tools.builtin.todo import TodosTool
from agentforge_harness.ui.plain import TUI, PlainTUI, get_console

console = get_console()


class CLI:
    def __init__(self, config: Config):
        self.agent: Agent | None = None
        self.tui = TUI(config=config, console=console)
        self.config = config
        self._last_user_message: str = ""

    async def run_single(self, message: str) -> str | None:
        async with Agent(config=self.config) as agent:
            self.agent = agent
            return await self._process_message(message)

    async def run_interactive(self) -> str | None:
        self.tui.print_welcome(
            "AgentForge",
            lines=[
                f"model: {self.config.model_name}",
                f"cwd: {self.config.cwd}",
                f"approval: {self.config.approval.value}",
                "commands: /help /doctor /provider /models /model /fallbacks /paths /compact /errors /new /reload /version /plan /build /name /skills /tools /mcp /stats /report /todos /thinking /branch /exit",
            ],
            mode=AgentMode.BUILD.value,
        )

        async with Agent(config=self.config) as agent:
            self.agent = agent

            while True:
                try:
                    mode = self.agent.session.mode.value if self.agent and self.agent.session else "build"
                    turn = self.agent.session._turn_count if self.agent and self.agent.session else 0
                    tool = self.agent.session.tool_registry.get("todos") if self.agent and self.agent.session else None
                    todo_count = len(tool._todos) if isinstance(tool, TodosTool) else 0

                    mode_color = "tool.read" if mode == "plan" else "tool.shell"
                    todo_style = "success" if todo_count == 0 else "warning"
                    prompt = (
                        f"\n[{mode_color}]◆ {mode.upper()}  #{turn}[/{mode_color}]"
                        f" [{todo_style}]● {todo_count}[/{todo_style}]"
                        f" [user]❯[/user] "
                    )
                    user_input = (await asyncio.to_thread(console.input, prompt)).strip()
                    if not user_input:
                        continue
                    if user_input.startswith("/"):
                        should_continue = await self._handle_command(user_input)
                        if not should_continue:
                            break
                        continue
                    self._last_user_message = user_input
                    await self._process_message(user_input)

                except KeyboardInterrupt:
                    console.print("\n[dim]Use /exit to quit[/dim]")
                except asyncio.CancelledError:
                    raise
                except EOFError:
                    break
        console.print("\n[dim]GoodBye![/dim]")
        return None

    def _get_tool_kind(self, tool_name: str) -> str | None:
        if not self.agent or not self.agent.session:
            return None
        tool = self.agent.session.tool_registry.get(tool_name)
        if not tool:
            return None
        return tool.kind.value

    # ------------------------------------------------------------------
    # Command dispatch
    # ------------------------------------------------------------------

    async def _handle_command(self, command: str) -> bool:
        parts = command.split(maxsplit=1)
        name = parts[0].lower()
        argument = parts[1].strip() if len(parts) > 1 else ""

        ctx = CommandContext(
            session=self.agent.session if self.agent else None,
            config=self.config,
            agent=self.agent,
            last_user_message=self._last_user_message,
        )

        result = await get_registry().dispatch(name, argument, ctx)

        if not result.handled:
            known = get_registry().known_commands
            matches = difflib.get_close_matches(name, known, n=3, cutoff=0.4)
            msg = f"Unknown command: {name}"
            if matches:
                msg += f"\nDid you mean: {', '.join(matches)}?"
            msg += "\nRun /help to see available commands."
            self.tui.show_error(msg)
            return True

        await self._render_result(result, argument)
        return not result.exit

    async def _render_result(self, result: CommandResult, argument: str = "") -> None:
        """Map a CommandResult to TUI calls.  Handles lifecycle signals too."""

        # Errors and notices
        if result.error:
            self.tui.show_error(result.error, result.error_title)
        if result.notice:
            self.tui.show_notice(result.notice, result.notice_title)

        # Lifecycle / mutation signals
        if result.switch_mode:
            self.tui.show_mode(result.switch_mode)

        if result.retry:
            self.tui.show_notice(f"Retrying: {self._last_user_message[:120]}", "Retry")
            await self._process_message(self._last_user_message)

        # /reload — CLI must update its own self.config reference
        if result.data_type == "reload_config" and result.data is not None:
            self.config = result.data
            return

        # Structured data display
        dt = result.data_type
        data = result.data

        if dt == "help":
            self.tui.show_help()

        elif dt == "config":
            self.tui.show_config(self._redact_config(data))

        elif dt == "doctor":
            from agentforge_harness.cli.doctor import print_doctor_report
            report = data["report"]
            if data.get("fix") and data.get("fix_messages"):
                self.tui.show_notice("\n".join(data["fix_messages"]), "Doctor fix")
            print_doctor_report(report, console=console)

        elif dt == "key_values":
            self.tui.show_key_values(
                data["title"],
                data["rows"],
                footer=data.get("footer"),
                border_style=data.get("border_style", "border"),
            )

        elif dt == "models":
            self.tui.show_models(
                provider=data["provider"],
                current_model=data["current_model"],
                models=data["models"],
                live=data["live"],
                message=data["message"],
                page=data["page"],
                total_pages=data["total_pages"],
                total_count=data["total_count"],
            )

        elif dt == "tools":
            self.tui.show_tools(data)

        elif dt == "skills":
            self.tui.show_notice("Scanning skill roots and building skill index...", "Skills")
            self.tui.show_skills(data["skills"], data["active"])
            self.tui.show_notice(
                f"Loaded {len(data['skills'])} skill(s) from discovered roots", "Skills"
            )

        elif dt == "mcp_servers":
            self.tui.show_mcp_servers(data)

        elif dt == "sessions":
            self.tui.show_sessions(
                data["items"],
                page=data["page"],
                total_pages=data["total_pages"],
                total_count=data["total_count"],
            )

        elif dt == "checkpoints":
            self.tui.show_checkpoints(
                data["items"],
                page=data["page"],
                total_pages=data["total_pages"],
                total_count=data["total_count"],
            )

        elif dt == "history":
            self.tui.show_notice("\n".join(data["lines"]), "History")

        elif dt == "stats":
            self.tui.show_stats(data)

        elif dt == "branch_choices":
            self.tui.show_branch_choices(data)

        elif dt == "report":
            if data["is_json"]:
                console.file.write(data["text"])
            else:
                self.tui.show_notice(data["text"], "Session Report")

        elif dt == "todos":
            self.tui.show_todos_list(data)

    # ------------------------------------------------------------------
    # Message processing
    # ------------------------------------------------------------------

    async def _process_message(self, message: str) -> str | None:
        if not self.agent:
            return None

        assistant_streaming = False
        final_response: str | None = None

        await self._auto_activate_skills(message)

        async for event in self.agent.run(message):
            if event.type == AgentEventType.TEXT_DELTA:
                content = event.data.get("content", "")
                if not assistant_streaming:
                    self.tui.begin_assistant()
                    assistant_streaming = True
                self.tui.stream_assistant_delta(content)

            elif event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content", "")
                if assistant_streaming:
                    self.tui.end_assistant()
                    assistant_streaming = False

            elif event.type == AgentEventType.AGENT_ERROR:
                error = event.data.get("error", "Unknown error")
                console.print(f"[error]Error: {error}[/error]")

            elif event.type == AgentEventType.TOOL_CALL_START:
                tool_name = event.data.get("name", "unknown")
                tool_kind = self._get_tool_kind(tool_name)
                self.tui.tool_call_start(
                    event.data.get("call_id", ""),
                    tool_name,
                    tool_kind,
                    event.data.get("arguments", {}),
                )

            elif event.type == AgentEventType.TOOL_CALL_COMPLETE:
                tool_name = event.data.get("name", "unknown")
                tool_kind = self._get_tool_kind(tool_name)
                metadata: dict[str, Any] = event.data.get("metadata") or {}
                diff: str | None = event.data.get("diff")
                self.tui.tool_call_complete(
                    event.data.get("call_id", ""),
                    tool_name,
                    tool_kind,
                    event.data.get("success", False),
                    event.data.get("output", ""),
                    event.data.get("error"),
                    metadata,
                    truncated=event.data.get("truncated", False),
                    diff=diff,
                    exit_code=event.data.get("exit_code"),
                )

        self.agent.session.save_session()
        return final_response

    async def _auto_activate_skills(self, message: str) -> None:
        if not self.agent or not self.agent.session:
            return

        matches = self.agent.session.skills_manager.suggest_skill_matches(message, limit=3)
        if matches and not matches[0].explicit:
            matches = matches[:1]

        for match in matches:
            skill = match.skill
            if skill.name in self.agent.session.active_skills:
                continue
            body = self.agent.session.activate_skill(skill.name)
            self.tui.show_notice(
                "\n".join([
                    f"Activated skill: {skill.name}",
                    f"Reason: {match.reason}",
                    f"File: {skill.path}",
                    f"Loaded {len(body.splitlines())} lines into prompt context.",
                ]),
                "Skills",
            )

    def _redact_config(self, value: Any) -> Any:
        secret_markers = ("key", "token", "secret", "password")
        if isinstance(value, dict):
            return {
                k: "[redacted]" if any(m in k.lower() for m in secret_markers) else self._redact_config(v)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [self._redact_config(item) for item in value]
        return value
