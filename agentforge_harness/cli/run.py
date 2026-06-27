import asyncio
import sys
import click
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError
from agentforge_harness.agent.persistence import PersistenceManager
from agentforge_harness.cli.commands import CLI
from agentforge_harness.cli.doctor import build_doctor_report, print_doctor_report
from agentforge_harness.cli.report import build_session_report, format_session_report, report_to_json
from agentforge_harness.cli.setup import run_setup
from agentforge_harness.config.loader import load_config
from agentforge_harness.ui.plain import get_console

console = get_console()

try:
    VERSION = version("agentforge-harness")
except PackageNotFoundError:
    VERSION = "0.1.0"


SHELL_COMPLETION_INSTRUCTIONS = {
    "bash": (
        "# Add this to your ~/.bashrc or ~/.bash_profile:\n"
        '# eval "$(_AGENTFORGE_COMPLETE=bash_source agentforge)"'
    ),
    "zsh": (
        "# Add this to your ~/.zshrc:\n"
        '# eval "$(_AGENTFORGE_COMPLETE=zsh_source agentforge)"'
    ),
    "fish": (
        "# Add this to your ~/.config/fish/config.fish:\n"
        "# eval (env _AGENTFORGE_COMPLETE=fish_source agentforge)"
    ),
}


@click.group(invoke_without_command=True)
@click.version_option(version=VERSION, prog_name="AgentForge")
@click.pass_context
def cli(ctx: click.Context) -> None:
    if ctx.invoked_subcommand is None:
        ctx.invoke(run)


@cli.command()
def init() -> None:
    """Run the setup wizard to configure API key and settings."""
    success = run_setup()
    sys.exit(0 if success else 1)


@cli.command()
@click.option(
    "--cwd",
    "-c",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Current working directory",
)
@click.option("--json", "json_output", is_flag=True, help="Print machine-readable JSON.")
def doctor(cwd: Path | None, json_output: bool) -> None:
    """Check local AgentForge configuration and runtime readiness."""
    try:
        config = load_config(cwd)
    except Exception as e:
        console.print(f"[error]Configuration Error : {e}[/error]")
        sys.exit(1)

    report = build_doctor_report(config)
    print_doctor_report(report, console=console, json_output=json_output)
    sys.exit(1 if report.has_errors else 0)


@cli.command()
@click.option("--session-id", help="Session id to report. Defaults to latest session.")
@click.option("--json", "json_output", is_flag=True, help="Print machine-readable JSON.")
@click.option(
    "--data-dir",
    type=click.Path(file_okay=False, path_type=Path),
    help="AgentForge data directory. Defaults to the platform data dir.",
)
def report(session_id: str | None, json_output: bool, data_dir: Path | None) -> None:
    """Print a saved session report without calling a model."""
    persistence = PersistenceManager(data_dir=data_dir)

    target_session_id = session_id
    if target_session_id is None:
        sessions = persistence.list_sessions()
        if not sessions:
            console.print("[error]No saved sessions found.[/error]")
            sys.exit(1)
        target_session_id = sessions[0]["session_id"]

    try:
        snapshot = persistence.load_session(target_session_id)
    except ValueError as exc:
        console.print(f"[error]{exc}[/error]")
        sys.exit(1)

    if snapshot is None:
        console.print(f"[error]Session not found: {target_session_id}[/error]")
        sys.exit(1)

    payload = build_session_report(snapshot)
    if json_output:
        console.file.write(report_to_json(payload))
    else:
        console.print(format_session_report(payload))


@cli.command()
@click.argument("prompt", required=False)
@click.option(
    "--cwd",
    "-c",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Current working directory",
)
@click.option("--plain", is_flag=True, default=False, help="Use plain Rich renderer (no Textual TUI).")
def run(prompt: str | None, cwd: Path | None, plain: bool = False) -> None:
    """Start AgentForge in interactive or single-prompt mode."""
    try:
        config = load_config(cwd)
    except Exception as e:
        console.print(f"[error]Configuration Error : {e}[/error]")
        sys.exit(1)

    if not config.api_key:
        console.print()
        console.print("[warning]No API key configured.[/warning]")
        console.print("Run [bold]agentforge init[/bold] to set up your API key and configuration.")
        console.print(
            "Or set the provider-specific key, such as "
            "[bold]OPENROUTER_API_KEY[/bold], [bold]OPENAI_API_KEY[/bold], "
            "or [bold]ANTHROPIC_API_KEY[/bold]."
        )
        console.print()
        sys.exit(1)

    errors = config.validate()
    if errors:
        for error in errors:
            console.print(f"[error]Configuration Error : {error}[/error]")
        sys.exit(1)

    if plain or prompt:
        cli_obj = CLI(config)
        if prompt:
            result = asyncio.run(cli_obj.run_single(prompt))
            if result is None:
                sys.exit(1)
        else:
            asyncio.run(cli_obj.run_interactive())
    else:
        from agentforge_harness.ui.tui import run_tui
        asyncio.run(run_tui(config=config))


@cli.command()
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
def completion(shell: str) -> None:
    """Print shell completion script for the given shell.

    Add the suggested line to your shell's rc file for tab completion.
    """
    instructions = SHELL_COMPLETION_INSTRUCTIONS.get(shell, "")
    console.print(instructions)
