from agent.agent import Agent
import asyncio
import click
from typing import Any
import sys
from agent.events import AgentEventType
from config.config import ApprovalPolicy, Config
from config.loader import load_config
from ui.tui import TUI, get_console
from pathlib import Path


console = get_console()


class CLI:
    def __init__(self, config: Config):
        self.agent: Agent | None = None
        self.tui = TUI(config=config, console=console)
        self.config = config

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
                "commands: /help /skills /skill /unskill /tools /mcp /stats /exit",
            ],
        )

        async with Agent(config=self.config) as agent:
            self.agent = agent

            while True:
                try:
                    user_input = console.input("\n[user]>[/user] ").strip()
                    if not user_input:
                        continue
                    if user_input.startswith("/"):
                        should_continue = self._handle_command(user_input)
                        if not should_continue:
                            break
                        continue
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

    def _handle_command(self, command: str) -> bool:
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
        if name == "/stats":
            if self.agent:
                usage = self.agent.session.context_manager.get_total_usage()
                self.tui.show_stats(
                    {
                        "turns": self.agent.session._turn_count,
                        "prompt_tokens": usage.prompt_tokens,
                        "completion_tokens": usage.completion_tokens,
                        "total_tokens": usage.total_tokens,
                        "cached_tokens": usage.cached_tokens,
                    }
                )
            return True

        self.tui.show_error(f"Unknown command: {name}\nRun /help to see available commands.")
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


async def run(messages: list[dict[str, Any]]):
    pass


@click.command()
@click.argument("prompt", required=False)
@click.option(
    "--cwd",
    "-c",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Current working directory",
)
def main(prompt: str | None, cwd: Path | None):

    try:
        config = load_config(cwd)
    except Exception as e:
        console.print(f"[error]Configuration Error : {e}[/error]")
        sys.exit(1)

    errors = config.validate()

    if errors:
        for error in errors:
            console.print(f"[error]Configuration Error : {error}[/error]")

        sys.exit(1)
    cli = CLI(config)

    if prompt:
        result = asyncio.run(cli.run_single(prompt))

        if result is None:
            sys.exit(1)
    else:
        asyncio.run(cli.run_interactive())

if __name__ == "__main__":
    main()
