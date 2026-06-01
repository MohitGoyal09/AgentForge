from agentforge_harness.agent.agent import Agent
import asyncio
import difflib
from typing import Any
from agentforge_harness.agent.events import AgentEventType
from agentforge_harness.agent.modes import AgentMode
from agentforge_harness.cli.report import (
    build_session_report,
    format_session_report,
    report_to_json,
    write_session_export,
)
from agentforge_harness.config.config import ApprovalPolicy, Config
from agentforge_harness.tools.base import ToolInvocation
from agentforge_harness.tools.builtin.todo import TodosTool
from agentforge_harness.ui.tui import TUI, get_console
from pathlib import Path

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
                "commands: /help /doctor /new /reload /version /plan /build /name /skills /tools /mcp /stats /report /todos /exit",
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
                    user_input = console.input(prompt).strip()
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
                except EOFError:
                    break
        console.print("\n[dim]GoodBye![/dim]")
        return

    def _get_tool_kind(self, tool_name: str) -> str | None:
        if not self.agent or not self.agent.session:
            return None
        tool = self.agent.session.tool_registry.get(tool_name)
        if not tool:
            return None
        return tool.kind.value

    async def _handle_command(self, command: str) -> bool:
        parts = command.split(maxsplit=1)
        name = parts[0].lower()
        argument = parts[1].strip() if len(parts) > 1 else ""

        if name in {"/exit", "/quit"}:
            return False
        if name == "/help":
            self.tui.show_help()
            return True
        if name == "/clear":
            if self.agent and self.agent.session.context_manager:
                self.agent.session.context_manager.clear()
            self.tui.show_notice("Conversation history cleared")
            return True
        if name == "/config":
            self.tui.show_config(self._redact_config(self.config.to_dict()))
            return True
        if name == "/doctor":
            from agentforge_harness.cli.doctor import build_doctor_report, print_doctor_report

            print_doctor_report(
                build_doctor_report(self.config),
                console=console,
            )
            return True
        if name == "/model":
            if not argument:
                self.tui.show_notice(f"Current model: {self.config.model_name}", "Model")
            else:
                self.config.model_name = argument
                self.tui.show_notice(f"Model set to: {self.config.model_name}", "Model")
            return True
        if name == "/approval":
            if not argument:
                modes = ", ".join(policy.value for policy in ApprovalPolicy)
                self.tui.show_notice(
                    f"Current approval: {self.config.approval.value}\nModes: {modes}",
                    "Approval",
                )
                return True
            try:
                self.config.approval = ApprovalPolicy(argument)
                if self.agent:
                    self.agent.session.approval_manager.approval_policy = self.config.approval
                self.tui.show_notice(f"Approval set to: {self.config.approval.value}", "Approval")
            except ValueError:
                self.tui.show_error(f"Unknown approval mode: {argument}")
            return True
        if name == "/tools":
            if self.agent:
                self.tui.show_tools(self.agent.session.tool_registry.get_tools())
            return True
        if name == "/skills":
            if self.agent:
                self.tui.show_notice("Scanning skill roots and building skill index...", "Skills")
                self.tui.show_skills(
                    self.agent.session.list_skills(),
                    self.agent.session.active_skills,
                )
                self.tui.show_notice(
                    f"Loaded {len(self.agent.session.list_skills())} skill(s) from discovered roots",
                    "Skills",
                )
            return True
        if name == "/skill":
            if not self.agent:
                return True
            if not argument:
                self.tui.show_error("Usage: /skill <name>")
                return True
            try:
                skill = self.agent.session.skills_manager.get_skill(argument)
                body = self.agent.session.activate_skill(argument)
                self.tui.show_notice(
                    "\n".join(
                        [
                            f"Activated skill: {argument}",
                            "Reason: manual command",
                            f"File: {skill.path}",
                            f"Loaded {len(body.splitlines())} lines into prompt context.",
                        ]
                    ),
                    "Skill",
                )
            except (KeyError, ValueError) as e:
                self.tui.show_error(str(e))
            return True
        if name == "/unskill":
            if not self.agent:
                return True
            if not argument:
                self.tui.show_error("Usage: /unskill <name>")
                return True
            if self.agent.session.deactivate_skill(argument):
                self.tui.show_notice(f"Unloaded skill from active context: {argument}", "Skill")
            else:
                self.tui.show_error(f"Skill is not active: {argument}")
            return True
        if name == "/mcp":
            if self.agent:
                self.tui.show_mcp_servers(self.agent.session.mcp_manager.get_all_servers())
            return True
        if name == "/name":
            if not self.agent or not self.agent.session:
                return True
            if not argument:
                label = self.agent.session.name or self.agent.session.session_id
                self.tui.show_notice(f"Session name: {label}", "Session")
            else:
                self.agent.session.name = argument
                self.tui.show_notice(f"Session renamed to: {argument}", "Session")
            return True
        if name == "/save":
            if self.agent:
                self.agent.session.save_session()
                self.tui.show_notice(f"Saved session: {self.agent.session.session_id}")
            return True
        if name == "/sessions":
            if self.agent:
                self.tui.show_sessions(self.agent.session.persistence.list_sessions())
            return True
        if name == "/resume":
            if not self.agent:
                return True
            if not argument:
                self.tui.show_error("Usage: /resume <session_id>")
                return True
            try:
                snapshot = self.agent.session.persistence.load_session(argument)
            except ValueError as e:
                self.tui.show_error(str(e))
                return True
            if not snapshot:
                self.tui.show_error(f"Session not found: {argument}")
                return True
            self.agent.session.restore_snapshot(snapshot)
            self.tui.show_notice(f"Resumed session: {snapshot.session_id}")
            return True
        if name == "/checkpoint":
            if self.agent:
                checkpoint_id = self.agent.session.save_checkpoint()
                self.tui.show_notice(f"Created checkpoint: {checkpoint_id}")
            return True
        if name == "/checkpoints":
            if self.agent:
                self.tui.show_checkpoints(self.agent.session.persistence.list_checkpoints())
            return True
        if name == "/restore":
            if not self.agent:
                return True
            if not argument:
                self.tui.show_error("Usage: /restore <checkpoint_id>")
                return True
            try:
                snapshot = self.agent.session.persistence.load_checkpoint(argument)
            except ValueError as e:
                self.tui.show_error(str(e))
                return True
            if not snapshot:
                self.tui.show_error(f"Checkpoint not found: {argument}")
                return True
            self.agent.session.restore_snapshot(snapshot)
            self.tui.show_notice(f"Restored checkpoint: {argument}")
            return True
        if name == "/new":
            if self.agent and self.agent.session:
                self.agent.session.reset()
                self.tui.show_notice("Session reset to clean state")
            return True

        if name == "/reload":
            if self.agent and self.agent.session:
                from agentforge_harness.config.loader import load_config
                try:
                    new_config = load_config(self.config.cwd)
                except Exception as e:
                    self.tui.show_error(f"Config reload failed: {e}")
                    return True
                self.config = new_config
                self.agent.config = new_config
                self.agent.session.config = new_config
                self.agent.session.approval_manager.approval_policy = new_config.approval
                self.agent.session.approval_manager.cwd = new_config.cwd
                if self.agent.session.context_manager:
                    self.agent.session.context_manager.config = new_config
                    self.agent.session.context_manager.refresh_system_prompt(
                        tools=self.agent.session.tool_registry.get_tools(mode=self.agent.session.mode),
                        mode=self.agent.session.mode,
                        skills=self.agent.session.skills_manager.list_skills(),
                        active_skills=self.agent.session.active_skills,
                        active_skill_bodies=self.agent.session.skills_manager.get_active_skill_bodies(self.agent.session.active_skills),
                    )
                self.tui.show_notice(
                    f"Config reloaded: model={new_config.model_name}, approval={new_config.approval.value}"
                )
            return True

        if name == "/version":
            from agentforge_harness.cli.run import VERSION
            self.tui.show_notice(f"AgentForge {VERSION}", "Version")
            return True

        if name == "/retry":
            if self._last_user_message:
                self.tui.show_notice(f"Retrying: {self._last_user_message[:120]}", "Retry")
                await self._process_message(self._last_user_message)
            else:
                self.tui.show_error("No previous message to retry")
            return True

        if name == "/history":
            if self.agent and self.agent.session and self.agent.session.context_manager:
                msgs = self.agent.session.context_manager._messages
                n = 10
                if argument:
                    try:
                        n = int(argument)
                    except ValueError:
                        pass
                recent = msgs[-n:] if len(msgs) > n else msgs
                lines = [f"=== Last {len(recent)} message(s) ==="]
                for msg in recent:
                    preview = msg.content[:200].replace("\n", "\\n") if msg.content else ""
                    tc = msg.token_count or ""
                    if msg.role == "tool" and msg.tool_call_id:
                        lines.append(f"  [{msg.role}] ({msg.tool_call_id[:8]}): {preview}" + (f" [{tc}t]" if tc else ""))
                    else:
                        n_calls = len(msg.tool_calls) if msg.tool_calls else 0
                        calls = f" [{n_calls} tool call(s)]" if n_calls else ""
                        lines.append(f"  [{msg.role}]{calls}: {preview}" + (f" [{tc}t]" if tc else ""))
                self.tui.show_notice("\n".join(lines), "History")
            else:
                self.tui.show_error("No active session")
            return True

        if name == "/report":
            if self.agent and self.agent.session:
                s = self.agent.session
                snapshot = s.create_snapshot(mode=s.mode.value)
                report = build_session_report(snapshot)
                if argument == "--json":
                    console.file.write(report_to_json(report))
                else:
                    self.tui.show_notice(format_session_report(report), "Session Report")
            else:
                self.tui.show_error("No active session")
            return True

        if name == "/plan":
            if self.agent and self.agent.session:
                self.agent.session.set_mode(AgentMode.PLAN)
                self.tui.show_mode(AgentMode.PLAN.value)
            return True
        if name == "/build":
            if self.agent and self.agent.session:
                self.agent.session.set_mode(AgentMode.BUILD)
                self.tui.show_mode(AgentMode.BUILD.value)
            return True

        if name == "/todos":
            if self.agent and self.agent.session:
                tool = self.agent.session.tool_registry.get("todos")
                if isinstance(tool, TodosTool):
                    if argument == "--clear":
                        count = len(tool._todos)
                        tool._todos.clear()
                        self.tui.show_notice(f"Cleared {count} todo(s)", "Todos")
                    else:
                        items = [(tid, c) for tid, c in tool._todos.items()]
                        self.tui.show_todos_list(items)
                else:
                    self.tui.show_todos_list([])
            return True

        if name == "/stats":
            if self.agent:
                usage = self.agent.session.context_manager.get_total_usage()
                tool = self.agent.session.tool_registry.get("todos")
                todo_count = len(tool._todos) if isinstance(tool, TodosTool) else 0
                self.tui.show_stats(
                    {
                        "turns": self.agent.session._turn_count,
                        "mode": self.agent.session.mode.value,
                        "todos": todo_count,
                        "prompt_tokens": usage.prompt_tokens,
                        "completion_tokens": usage.completion_tokens,
                        "total_tokens": usage.total_tokens,
                        "cached_tokens": usage.cached_tokens,
                    }
                )
            return True

        if name == "/export":
            if not self.agent or not self.agent.session:
                return True
            fmt = argument or "markdown"
            if fmt not in ("markdown", "md", "html"):
                self.tui.show_error(f"Unknown export format: {fmt}")
                return True

            s = self.agent.session
            snapshot = s.create_snapshot(mode=s.mode.value)
            out_path = write_session_export(snapshot, Path.cwd(), fmt)
            self.tui.show_notice(f"Exported session to: {out_path}", "Export")
            return True

        known = [
            "/help", "/exit", "/quit", "/clear", "/config", "/model",
            "/doctor", "/approval", "/stats", "/todos", "/tools", "/skills", "/skill",
            "/unskill", "/mcp", "/name", "/save", "/sessions", "/resume",
            "/checkpoint", "/checkpoints", "/restore", "/plan", "/build",
            "/new", "/reload", "/version", "/retry", "/history", "/report",
            "/export",
        ]
        matches = difflib.get_close_matches(name, known, n=3, cutoff=0.4)
        msg = f"Unknown command: {name}"
        if matches:
            msg += f"\nDid you mean: {', '.join(matches)}?"
        msg += "\nRun /help to see available commands."
        self.tui.show_error(msg)
        return True

    def _redact_config(self, value: Any) -> Any:
        secret_markers = ("key", "token", "secret", "password")
        if isinstance(value, dict):
            redacted = {}
            for key, item in value.items():
                if any(marker in key.lower() for marker in secret_markers):
                    redacted[key] = "[redacted]"
                else:
                    redacted[key] = self._redact_config(item)
            return redacted
        if isinstance(value, list):
            return [self._redact_config(item) for item in value]
        return value

    async def _process_message(self, message: str) -> str | None:
        if not self.agent:
            return None

        assistant_streaming = False
        final_response: str | None = None

        await self._auto_activate_skills(message)

        async for event in self.agent.run(message):
            self.agent.session.record_event(event.type.value, event.data)

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
                "\n".join(
                    [
                        f"Activated skill: {skill.name}",
                        f"Reason: {match.reason}",
                        f"File: {skill.path}",
                        f"Loaded {len(body.splitlines())} lines into prompt context.",
                    ]
                ),
                "Skills",
            )
