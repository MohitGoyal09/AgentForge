from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.text import Text
from rich import box
from config.loader import get_config_dir

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "minimax/minimax-m2.5:free"

console = Console()


def _write_env_file(env_path: Path, api_key: str, base_url: str, model: str) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"OPENROUTER_API_KEY={api_key}",
        f"OPENROUTER_BASE_URL={base_url}",
        "",
    ]
    env_path.write_text("\n".join(lines), encoding="utf-8")


def run_setup() -> bool:
    config_dir = get_config_dir()
    env_path = config_dir / ".env"

    console.print()
    console.print(
        Panel(
            Text(
                "Welcome to AgentForge!\n\n"
                "You need an API key to use LLM-powered features.\n"
                "AgentForge uses OpenRouter by default, which supports\n"
                "many models including Claude, GPT, Gemini, and more.\n\n"
                "Get a free key at: https://openrouter.ai/keys",
                style="code",
            ),
            title=Text("Setup", style="bold cyan"),
            border_style="bright_cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )
    console.print()

    api_key = Prompt.ask("API key", password=True)
    if not api_key:
        console.print("[error]API key is required.[/error]")
        return False

    base_url = Prompt.ask("Base URL (OpenRouter)", default=DEFAULT_BASE_URL)
    model = Prompt.ask("Default model", default=DEFAULT_MODEL)

    _write_env_file(env_path, api_key, base_url, model)

    console.print()
    console.print(
        Panel(
            Text(
                f"Configuration saved to: {env_path}\n\n"
                f"API key: [green]configured[/green]\n"
                f"Base URL: {base_url}\n"
                f"Model: {model}\n\n"
                "You can change these later by editing the file above,\n"
                "setting environment variables, or running [bold]agentforge init[/bold] again.",
                style="code",
            ),
            title=Text("Setup complete", style="bold green"),
            border_style="green",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )
    return True
