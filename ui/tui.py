from pathlib import Path
import json
from typing import Any
from rich.console import Console
from rich.theme import Theme
from rich.rule import Rule
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.prompt import Prompt
from rich.console import Group
from rich.align import Align
from rich.syntax import Syntax
from rich.markdown import Markdown
from config.config import Config
from tools.base import ToolConfirmation
from utils.paths import display_path_rel_to_cwd
import re

from utils.text import truncate_text

AGENTFORGE_ASCII = r"""
        █████╗  ██████╗ ███████╗███╗   ██╗████████╗
       ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
       ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   
       ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   
       ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   
       ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   
         ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
         ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
         █████╗  ██║   ██║██████╔╝██║  ███╗█████╗  
         ██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝  
         ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
         ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝
""".strip("\n")

AGENT_THEME = Theme(
    {
        # General
        "info": "cyan",
        "warning": "yellow",
        "error": "bright_red bold",
        "success": "green",
        "dim": "dim",
        "muted": "grey50",
        "border": "grey35",
        "highlight": "bold cyan",
        # Roles
        "user": "bright_blue bold",
        "assistant": "bright_white",
        # Tools
        "tool": "bright_magenta bold",
        "tool.read": "cyan",
        "tool.write": "yellow",
        "tool.shell": "magenta",
        "tool.network": "bright_blue",
        "tool.memory": "green",
        "tool.mcp": "bright_cyan",
        # Code / blocks
        "code": "white",
    }
)

_console: Console | None = None


def get_console() -> Console:
    global _console
    if _console is None:
        _console = Console(theme=AGENT_THEME, highlight=False)

    return _console


class TUI:
    def __init__(
        self,
        config: Config,
        console: Console | None = None,
    ) -> None:
        self.console = console or get_console()
        self._assistant_stream_open = False
        self._tool_args_by_call_id: dict[str, dict[str, Any]] = {}
        self.config = config
        self.cwd = self.config.cwd
        self._max_block_tokens = 2500

    def begin_assistant(self) -> None:
        self.console.print()
        self.console.print(Rule(Text("Assistant", style="assistant")))
        self._assistant_stream_open = True

    def end_assistant(self) -> None:
        if self._assistant_stream_open:
            self.console.print()
        self._assistant_stream_open = False

    def stream_assistant_delta(self, content: str) -> None:
        self.console.print(content, end="", markup=False)

    def _ordered_args(self, tool_name: str, args: dict[str, Any]) -> list[tuple]:
        _PREFERRED_ORDER = {
            "read_file": ["path", "offset", "limit"],
            "write_file": ["path", "create_directories", "content"],
            "edit": ["path", "replace_all", "old_string", "new_string"],
            "shell": ["command", "timeout", "cwd"],
            "list_dir": ["path", "include_hidden"],
            "grep": ["path", "case_insensitive", "pattern"],
            "glob": ["path", "pattern"],
            "todos": ["id", "action", "content"],
            "memory": ["action", "key", "value"],
        }

        preferred = _PREFERRED_ORDER.get(tool_name, [])
        ordered: list[tuple[str, Any]] = []
        seen = set()

        for key in preferred:
            if key in args:
                ordered.append((key, args[key]))
                seen.add(key)

        remaining_keys = set(args.keys() - seen)
        ordered.extend((key, args[key]) for key in remaining_keys)

        return ordered

    def _render_args_table(self, tool_name: str, args: dict[str, Any]) -> Table:
        table = Table.grid(padding=(0, 1))
        table.add_column(style="muted", justify="right", no_wrap=True)
        table.add_column(style="code", overflow="fold")

        for key, value in self._ordered_args(tool_name, args):
            if isinstance(value, str):
                if key in {"content", "old_string", "new_string"}:
                    line_count = len(value.splitlines()) or 0
                    byte_count = len(value.encode("utf-8", errors="replace"))
                    value = f"<{line_count} lines • {byte_count} bytes>"

            if isinstance(value, bool):
                value = str(value).lower()
            elif isinstance(value, (int, float)):
                value = str(value)
            elif isinstance(value, dict):
                value = str(value)
            elif not isinstance(value, str):
                value = repr(value)

            table.add_row(key, value)

        return table

    def tool_call_start(
        self,
        call_id: str,
        name: str,
        tool_kind: str | None,
        arguments: dict[str, Any],
    ) -> None:
        self._tool_args_by_call_id[call_id] = arguments
        border_style = f"tool.{tool_kind}" if tool_kind else "tool"

        title = Text.assemble(
            ("⏺ ", "muted"),
            (name, "tool"),
            ("  ", "muted"),
            (f"#{call_id[:8]}", "muted"),
        )

        display_args = dict(arguments)
        for key in ("path", "cwd"):
            val = display_args.get(key)
            if isinstance(val, str) and self.cwd:
                display_args[key] = str(display_path_rel_to_cwd(val, self.cwd))

        panel = Panel(
            (
                self._render_args_table(name, display_args)
                if display_args
                else Text(
                    "(no args)",
                    style="muted",
                )
            ),
            title=title,
            title_align="left",
            subtitle=Text("running", style="muted"),
            subtitle_align="right",
            border_style=border_style,
            box=box.ROUNDED,
            padding=(1, 2),
        )
        self.console.print()
        self.console.print(panel)

    def _extract_read_file_code(self, text: str) -> tuple[int, str] | None:
        body = text
        if "\n\n" in text:
            possible_header, possible_body = text.split("\n\n", 1)
            if not re.match(r"^\s*\d+\|", possible_header) and re.match(
                r"^\s*\d+\|",
                possible_body,
            ):
                body = possible_body

        code_lines: list[str] = []
        start_line: int | None = None

        for line in body.splitlines():
            # 1|def main():
            # 2| print()
            m = re.match(r"^\s*(\d+)\|(.*)$", line)
            if not m:
                return None
            line_no = int(m.group(1))
            if start_line is None:
                start_line = line_no
            code_lines.append(m.group(2))

        if start_line is None:
            return None

        return start_line, "\n".join(code_lines)

    def _guess_language(self, path: str | None) -> str:
        if not path:
            return "text"
        suffix = Path(path).suffix.lower()
        return {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "jsx",
            ".ts": "typescript",
            ".tsx": "tsx",
            ".json": "json",
            ".toml": "toml",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
            ".sh": "bash",
            ".bash": "bash",
            ".zsh": "bash",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".kt": "kotlin",
            ".swift": "swift",
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".hpp": "cpp",
            ".css": "css",
            ".html": "html",
            ".xml": "xml",
            ".sql": "sql",
        }.get(suffix, "text")

    def print_welcome(self, title: str, lines: list[str], mode: str | None = None) -> None:
        logo_lines = AGENTFORGE_ASCII.split("\n")
        colored_logo_lines = []
        for i, line in enumerate(logo_lines):
            colors = ["bold cyan", "cyan", "bright_blue", "blue", "bright_magenta", "magenta"]
            c = colors[i % len(colors)]
            colored_logo_lines.append(Text(line, style=c))
        logo_text = Text("\n").join(colored_logo_lines)
        main_logo = Align.center(logo_text)

        info = Group(
            Text(""),
            Text("  AgentForge v0.1.0", style="bold white"),
            Text(""),
        )

        table = Table.grid(padding=(0, 2))
        table.add_column(style="muted", no_wrap=True)
        table.add_column(style="code", overflow="fold")

        for line in lines:
            if ":" in line:
                key, value = line.split(":", 1)
                table.add_row(key.strip(), value.strip())
            else:
                table.add_row("", line)

        if mode:
            mode_style = "tool.read" if mode == "plan" else "tool.shell"
            table.add_row("mode", f"[{mode_style}]{mode.upper()}[/{mode_style}]")

        self.console.print(
            Panel(
                Group(
                    main_logo,
                    info,
                    table,
                ),
                title=None,
                subtitle=Text("type /help for commands", style="muted"),
                subtitle_align="right",
                border_style="bright_cyan",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

        self.console.print(
            Panel(
                Text("AgentForge ready — what are we building today?", style="cyan"),
                border_style="border",
                box=box.ROUNDED,
                padding=(0, 2),
            )
        )

    def show_mode(self, mode: str) -> None:
        style = "tool.read" if mode == "plan" else "tool.shell"
        self.console.print(
            Panel(
                Text(f"Switched to {mode.upper()} mode", style="code"),
                title=Text("Mode", style=style),
                title_align="left",
                border_style=style,
                box=box.ROUNDED,
                padding=(0, 2),
            )
        )

    def show_notice(self, message: str, title: str = "Status") -> None:
        self.console.print(
            Panel(
                Text(message, style="code"),
                title=Text(title, style="highlight"),
                title_align="left",
                border_style="border",
                box=box.ROUNDED,
                padding=(0, 2),
            )
        )

    def show_error(self, message: str, title: str = "Error") -> None:
        self.console.print(
            Panel(
                Text(message, style="error"),
                title=Text(title, style="error"),
                title_align="left",
                border_style="error",
                box=box.ROUNDED,
                padding=(0, 2),
            )
        )

    def show_config(self, config: dict[str, Any]) -> None:
        body = json.dumps(config, indent=2)
        self.console.print(
            Panel(
                Syntax(body, "json", theme="monokai", word_wrap=True),
                title=Text("Configuration", style="highlight"),
                title_align="left",
                border_style="border",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

    def show_tools(self, tools: list[Any]) -> None:
        table = Table(
            box=box.SIMPLE,
            show_header=True,
            header_style="highlight",
            expand=True,
        )
        table.add_column("Tool", style="tool", no_wrap=True)
        table.add_column("Kind", style="muted", no_wrap=True)
        table.add_column("Description", style="code", overflow="fold")

        for tool in sorted(tools, key=lambda item: (item.kind.value, item.name)):
            description = tool.description
            if len(description) > 120:
                description = description[:117] + "..."
            table.add_row(tool.name, tool.kind.value, description)

        self.console.print(
            Panel(
                table if tools else Text("No tools registered", style="muted"),
                title=Text("Tools", style="highlight"),
                title_align="left",
                border_style="border",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

    def show_skills(
        self,
        skills: list[Any],
        active_skills: list[str] | None = None,
    ) -> None:
        active = set(active_skills or [])
        table = Table(
            box=box.SIMPLE,
            show_header=True,
            header_style="highlight",
            expand=True,
        )
        table.add_column("Skill", style="tool", no_wrap=True)
        table.add_column("State", style="muted", no_wrap=True)
        table.add_column("Description", style="code", overflow="fold")
        table.add_column("Tools", style="muted", overflow="fold")

        for skill in sorted(skills, key=lambda item: item.name):
            state = "active" if skill.name in active else "available"
            tools = ", ".join(skill.allowed_tools or [])
            table.add_row(skill.name, state, skill.description, tools or "-")

        self.console.print(
            Panel(
                table if skills else Text("No skills discovered", style="muted"),
                title=Text("Skills index", style="highlight"),
                title_align="left",
                border_style="border",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

    def show_mcp_servers(self, servers: list[dict[str, Any]]) -> None:
        table = Table(
            box=box.SIMPLE,
            show_header=True,
            header_style="highlight",
            expand=True,
        )
        table.add_column("Server", style="tool.mcp", no_wrap=True)
        table.add_column("Status", style="code", no_wrap=True)
        table.add_column("Tools", style="muted", justify="right")

        for server in servers:
            table.add_row(
                str(server.get("name", "")),
                str(server.get("status", "")),
                str(server.get("tools", 0)),
            )

        self.console.print(
            Panel(
                table if servers else Text("No MCP servers configured", style="muted"),
                title=Text("MCP Servers", style="highlight"),
                title_align="left",
                border_style="border",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

    def show_stats(self, stats: dict[str, Any]) -> None:
        table = Table.grid(padding=(0, 2))
        table.add_column(style="muted", no_wrap=True)
        table.add_column(style="code", justify="right")

        for key, value in stats.items():
            table.add_row(key.replace("_", " "), str(value))

        self.console.print(
            Panel(
                table,
                title=Text("Session Stats", style="highlight"),
                title_align="left",
                border_style="border",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

    def show_sessions(self, sessions: list[dict[str, Any]]) -> None:
        table = Table(
            box=box.SIMPLE,
            show_header=True,
            header_style="highlight",
            expand=True,
        )
        table.add_column("Session", style="code", overflow="fold")
        table.add_column("Updated", style="muted", no_wrap=True)
        table.add_column("Turns", style="code", justify="right")
        table.add_column("Mode", style="muted", no_wrap=True)
        table.add_column("CWD", style="code", overflow="fold")

        for session in sessions:
            table.add_row(
                str(session.get("session_id", "")),
                str(session.get("updated_at", "")),
                str(session.get("turn_count", 0)),
                str(session.get("mode", "")),
                str(session.get("cwd", "")),
            )

        self.console.print(
            Panel(
                table if sessions else Text("No saved sessions", style="muted"),
                title=Text("Saved Sessions", style="highlight"),
                title_align="left",
                border_style="border",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

    def show_checkpoints(self, checkpoints: list[dict[str, Any]]) -> None:
        table = Table(
            box=box.SIMPLE,
            show_header=True,
            header_style="highlight",
            expand=True,
        )
        table.add_column("Checkpoint", style="code", overflow="fold")
        table.add_column("Session", style="muted", overflow="fold")
        table.add_column("Turns", style="code", justify="right")
        table.add_column("Mode", style="muted", no_wrap=True)
        table.add_column("CWD", style="code", overflow="fold")

        for checkpoint in checkpoints:
            table.add_row(
                str(checkpoint.get("checkpoint_id", "")),
                str(checkpoint.get("session_id", "")),
                str(checkpoint.get("turn_count", 0)),
                str(checkpoint.get("mode", "")),
                str(checkpoint.get("cwd", "")),
            )

        self.console.print(
            Panel(
                table if checkpoints else Text("No checkpoints", style="muted"),
                title=Text("Checkpoints", style="highlight"),
                title_align="left",
                border_style="border",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

    def tool_call_complete(
        self,
        call_id: str,
        name: str,
        tool_kind: str | None,
        success: bool,
        output: str,
        error: str | None,
        metadata: dict[str, Any] | None,
        diff: str | None = None,
        truncated: bool = False,
        exit_code: int | None = None,
    ) -> None:
        border_style = f"tool.{tool_kind}" if tool_kind else "tool"
        status_icon = "✓" if success else "✗"
        status_style = "success" if success else "error"

        title = Text.assemble(
            (f"{status_icon} ", status_style),
            (name, "tool"),
            ("  ", "muted"),
            (f"#{call_id[:8]}", "muted"),
        )

        args = self._tool_args_by_call_id.get(call_id, {})

        primary_path = None
        blocks = []
        if isinstance(metadata, dict) and isinstance(metadata.get("path"), str):
            primary_path = metadata.get("path")

        if name == "read_file" and success:
            if primary_path:
                extracted = self._extract_read_file_code(output)

                if extracted:
                    start_line, code = extracted
                    shown_start = metadata.get("shown_start")
                    shown_end = metadata.get("shown_end")
                    total_lines = metadata.get("total_lines")
                    has_trailing_newline = metadata.get("has_trailing_newline")
                    pl = self._guess_language(primary_path)

                    header_parts = [display_path_rel_to_cwd(primary_path, self.cwd)]

                    if shown_start and shown_end and total_lines:
                        header_parts.append(
                            f"lines {shown_start}-{shown_end} of {total_lines}"
                        )
                    if has_trailing_newline is False and shown_end == total_lines:
                        header_parts.append("no trailing newline")

                    blocks.append(Text(" • ".join(header_parts), style="muted"))
                    blocks.append(
                        Syntax(
                            code,
                            pl,
                            theme="monokai",
                            line_numbers=True,
                            start_line=start_line,
                            word_wrap=True,
                        )
                    )
                else:
                    output_display = truncate_text(
                        output,
                        self.config.model_name,
                        self._max_block_tokens,
                    )
                    blocks.append(
                        Syntax(
                            output_display,
                            "text",
                            theme="monokai",
                            word_wrap=False,
                        )
                    )
            else:
                output_display = truncate_text(
                    output,
                    "",
                    self._max_block_tokens,
                )
                blocks.append(
                    Syntax(
                        output_display,
                        "text",
                        theme="monokai",
                        word_wrap=False,
                    )
                )
        elif name in {"write_file", "append_file", "edit", "apply_patch"} and success and diff:
            output_line = output.strip() if output.strip() else "Completed"
            blocks.append(Text(output_line, style="muted"))
            if metadata.get("fallback"):
                blocks.append(Text("applied with line-based fallback", style="warning"))
            diff_text = diff
            diff_display = truncate_text(
                diff_text,
                self.config.model_name,
                self._max_block_tokens,
            )
            blocks.append(
                Syntax(
                    diff_display,
                    "diff",
                    theme="monokai",
                    word_wrap=True,
                )
            )
        elif name == "shell" and success:
            command = args.get("command")
            if isinstance(command, str) and command.strip():
                blocks.append(Text(f"$ {command.strip()}", style="muted"))

            if exit_code is not None:
                blocks.append(Text(f"exit_code={exit_code}", style="muted"))

            output_display = truncate_text(
                output,
                self.config.model_name,
                self._max_block_tokens,
            )
            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                )
            )
        elif name == "list_dir" and success:
            entries = metadata.get("entries")
            path = metadata.get("path")
            summary = []
            if isinstance(path, str):
                summary.append(path)

            if isinstance(entries, int):
                summary.append(f"{entries} entries")

            if summary:
                blocks.append(Text(" • ".join(summary), style="muted"))

            output_display = truncate_text(
                output,
                self.config.model_name,
                self._max_block_tokens,
            )
            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                )
            )
        elif name == "grep" and success:
            matches = metadata.get("matches")
            files_searched = metadata.get("files_searched")
            summary = []
            if isinstance(matches, int):
                summary.append(f"{matches} matches")
            if isinstance(files_searched, int):
                summary.append(f"searched {files_searched} files")

            if summary:
                blocks.append(Text(" • ".join(summary), style="muted"))

            output_display = truncate_text(
                output, self.config.model_name, self._max_block_tokens
            )
            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                )
            )
        elif name == "glob" and success:
            matches = metadata.get("matches")
            if isinstance(matches, int):
                blocks.append(Text(f"{matches} matches", style="muted"))

            output_display = truncate_text(
                output,
                self.config.model_name,
                self._max_block_tokens,
            )
            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                )
            )
        elif name == "web_search" and success:
            results = metadata.get("results")
            query = args.get("query")
            summary = []
            if isinstance(query, str):
                summary.append(query)
            if isinstance(results, int):
                summary.append(f"{results} results")

            if summary:
                blocks.append(Text(" • ".join(summary), style="muted"))

            output_display = truncate_text(
                output,
                self.config.model_name,
                self._max_block_tokens,
            )
            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                )
            )
        elif name == "web_fetch" and success:
            status_code = metadata.get("status_code")
            content_length = metadata.get("content_length")
            url = args.get("url")
            summary = []
            if isinstance(status_code, int):
                summary.append(str(status_code))
            if isinstance(content_length, int):
                summary.append(f"{content_length} bytes")
            if isinstance(url, str):
                summary.append(url)

            if summary:
                blocks.append(Text(" • ".join(summary), style="muted"))

            output_display = truncate_text(
                output,
                self.config.model_name,
                self._max_block_tokens,
            )
            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                )
            )
        elif name == "todos" and success:
            output_display = truncate_text(
                output,
                self.config.model_name,
                self._max_block_tokens,
            )
            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                )
            )
        elif name == "memory" and success:
            action = args.get("action")
            key = args.get("key")
            found = metadata.get("found")
            summary = []
            if isinstance(action, str) and action:
                summary.append(action)
            if isinstance(key, str) and key:
                summary.append(key)
            if isinstance(found, bool):
                summary.append("found" if found else "missing")

            if summary:
                blocks.append(Text(" • ".join(summary), style="muted"))
            output_display = truncate_text(
                output,
                self.config.model_name,
                self._max_block_tokens,
            )
            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                )
            )
        else:
            if error and not success:
                blocks.append(Text(error, style="error"))

            output_display = truncate_text(
                output, self.config.model_name, self._max_block_tokens
            )
            if output_display.strip():
                blocks.append(
                    Syntax(
                        output_display,
                        "text",
                        theme="monokai",
                        word_wrap=True,
                    )
                )
            else:
                blocks.append(Text("(no output)", style="muted"))

        if truncated:
            blocks.append(Text("note: tool output was truncated", style="warning"))

        panel = Panel(
            Group(
                *blocks,
            ),
            title=title,
            title_align="left",
            subtitle=Text("done" if success else "failed", style=status_style),
            subtitle_align="right",
            border_style=border_style,
            box=box.ROUNDED,
            padding=(1, 2),
        )
        self.console.print()
        self.console.print(panel)

    def handle_confirmation(self, confirmation: ToolConfirmation) -> bool:
        output = [
            Text(confirmation.tool_name, style="tool"),
            Text(confirmation.description, style="code"),
        ]

        if confirmation.command:
            output.append(Text(f"$ {confirmation.command}", style="warning"))

        if confirmation.diff:
            diff_text = confirmation.diff.to_diff()
            output.append(
                Syntax(
                    diff_text,
                    "diff",
                    theme="monokai",
                    word_wrap=True,
                )
            )
        else:
            diff_text = confirmation.get_diff_text()
            if diff_text:
                output.append(
                    Syntax(
                        diff_text,
                        "diff",
                        theme="monokai",
                        word_wrap=True,
                    )
                )

        self.console.print()
        self.console.print(
            Panel(
                Group(*output),
                title=Text("Approval required", style="warning"),
                title_align="left",
                border_style="warning",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

        response = Prompt.ask(
            "\nApprove?", choices=["y", "n", "yes", "no"], default="n"
        )

        return response.lower() in {"y", "yes"}

    def show_help(self) -> None:
        help_text = """
## Commands

- `/help` - Show this help
- `/exit` or `/quit` - Exit the agent
- `/clear` - Clear conversation history
- `/config` - Show current configuration
- `/model <name>` - Change the model
- `/approval <mode>` - Change approval mode
- `/stats` - Show session statistics
- `/tools` - List available tools
- `/skills` - List available skills
- `/skill <name>` - Activate a skill
- `/unskill <name>` - Deactivate a skill
- `/mcp` - Show MCP server status
- `/plan` - Switch to plan mode (read-only, for designing a plan)
- `/build` - Switch to build mode (full tool access, for implementing)
- `/save` - Save current session
- `/checkpoint` - Create a checkpoint
- `/checkpoints` - List available checkpoints
- `/restore <checkpoint_id>` - Restore a checkpoint
- `/sessions` - List saved sessions
- `/resume <session_id>` - Resume a saved session

## Tips

- Just type your message to chat with the agent
- The agent can read, write, and execute code
- Some operations require approval (can be configured)
- Use `/plan` to design a plan before implementing with `/build`
"""
        self.console.print(Markdown(help_text))
