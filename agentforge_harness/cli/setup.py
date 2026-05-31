from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.text import Text
from rich import box
from agentforge_harness.config.loader import get_config_dir

PROVIDERS = ("openrouter", "openai", "anthropic", "custom")
DEFAULT_MODELS = {
    "openrouter": "minimax/minimax-m2.5:free",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-latest",
    "custom": "local/model",
}
DEFAULT_BASE_URLS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "",
    "anthropic": "",
    "custom": "http://localhost:11434/v1",
}
API_KEY_ENV = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "custom": "API_KEY",
}

console = Console()


def _write_env_file(env_path: Path, provider: str, api_key: str, base_url: str) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    api_key_env = API_KEY_ENV[provider]
    lines = [
        f"{api_key_env}={api_key}",
    ]
    if base_url:
        base_url_env = f"{provider.upper()}_BASE_URL" if provider != "custom" else "BASE_URL"
        lines.append(f"{base_url_env}={base_url}")
    lines.extend([
        "",
    ])
    env_path.write_text("\n".join(lines), encoding="utf-8")


def _write_config_file(config_path: Path, provider: str, model: str, base_url: str) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        'approval = "on-request"',
        "",
        "[model]",
        f'provider = "{provider}"',
        f'name = "{model}"',
    ]
    if base_url:
        lines.append(f'base_url = "{base_url}"')
    lines.append("")
    config_path.write_text("\n".join(lines), encoding="utf-8")


def run_setup() -> bool:
    config_dir = get_config_dir()
    env_path = config_dir / ".env"
    config_path = config_dir / "config.toml"

    console.print()
    console.print(
        Panel(
            Text(
                "Welcome to AgentForge!\n\n"
                "You need an API key to use LLM-powered features.\n"
                "OpenRouter is the default because it can route to many models,\n"
                "but you can also configure OpenAI, Anthropic, or any\n"
                "OpenAI-compatible endpoint.\n\n"
                "Provider keys:\n"
                "- OpenRouter: https://openrouter.ai/keys\n"
                "- OpenAI: https://platform.openai.com/api-keys\n"
                "- Anthropic: https://console.anthropic.com/settings/keys",
                style="code",
            ),
            title=Text("Setup", style="bold cyan"),
            border_style="bright_cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )
    console.print()

    provider = Prompt.ask(
        "Provider",
        choices=list(PROVIDERS),
        default="openrouter",
    )
    default_base_url = DEFAULT_BASE_URLS[provider]
    default_model = DEFAULT_MODELS[provider]

    api_key = Prompt.ask("API key", password=True)
    if not api_key:
        console.print("[error]API key is required.[/error]")
        return False

    base_url = Prompt.ask(
        "Base URL",
        default=default_base_url,
    ).strip()
    model = Prompt.ask("Default model", default=default_model)

    _write_env_file(env_path, provider, api_key, base_url)
    _write_config_file(config_path, provider, model, base_url)

    console.print()
    console.print(
        Panel(
            Text(
                f"Secrets saved to: {env_path}\n"
                f"Config saved to: {config_path}\n\n"
                f"Provider: {provider}\n"
                f"API key: [green]configured[/green]\n"
                f"Base URL: {base_url or 'provider default'}\n"
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
