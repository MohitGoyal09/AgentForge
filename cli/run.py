import asyncio
import sys
import click
from pathlib import Path
from cli.commands import CLI
from cli.setup import run_setup
from config.config import Config
from config.loader import load_config
from ui.tui import get_console

console = get_console()


@click.group(invoke_without_command=True)
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
@click.argument("prompt", required=False)
@click.option(
    "--cwd",
    "-c",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Current working directory",
)
def run(prompt: str | None, cwd: Path | None) -> None:
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
        console.print("Or set the [bold]OPENROUTER_API_KEY[/bold] environment variable.")
        console.print()
        sys.exit(1)

    errors = config.validate()
    if errors:
        for error in errors:
            console.print(f"[error]Configuration Error : {error}[/error]")
        sys.exit(1)

    cli_obj = CLI(config)

    if prompt:
        result = asyncio.run(cli_obj.run_single(prompt))
        if result is None:
            sys.exit(1)
    else:
        asyncio.run(cli_obj.run_interactive())
