from pathlib import Path
import os
from rich.prompt import Confirm, Prompt
from rich.panel import Panel
from rich.text import Text
from rich import box
from agentforge_harness.config.loader import get_config_dir
from agentforge_harness.ui.tui import get_console

PROVIDERS = ("openrouter", "openai", "anthropic", "custom")
PROVIDER_LABELS = {
    "openrouter": "OpenRouter",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "custom": "Custom OpenAI-compatible",
}
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
BASE_URL_ENV = {
    "openrouter": "OPENROUTER_BASE_URL",
    "openai": "OPENAI_BASE_URL",
    "anthropic": "ANTHROPIC_BASE_URL",
    "custom": "BASE_URL",
}
PROVIDER_HINTS = {
    "openrouter": (
        "OpenRouter routes through an OpenAI-compatible API. Model names usually look "
        "like provider/model, for example openai/gpt-4o-mini. AgentForge sets the "
        "OpenRouter base URL automatically."
    ),
    "openai": (
        "OpenAI uses the native OpenAI SDK path. The SDK default base URL is used."
    ),
    "anthropic": (
        "Anthropic uses the native Anthropic SDK path. The SDK default base URL is used."
    ),
    "custom": (
        "Custom providers must expose an OpenAI-compatible /v1 API, such as Ollama, "
        "vLLM, LM Studio, or another local gateway. AgentForge asks for the base URL "
        "before the API key for custom providers."
    ),
}

console = get_console()


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
    os.chmod(env_path, 0o600)


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
    os.chmod(config_path, 0o600)


def _existing_setup_files(env_path: Path, config_path: Path) -> list[Path]:
    return [path for path in (env_path, config_path) if path.exists()]


def _provider_help(provider: str) -> str:
    api_key_env = API_KEY_ENV[provider]
    base_url_env = BASE_URL_ENV[provider]
    default_model = DEFAULT_MODELS[provider]
    default_base_url = DEFAULT_BASE_URLS[provider] or "provider default"
    return (
        f"{PROVIDER_HINTS[provider]}\n\n"
        f"API key env: {api_key_env}\n"
        f"Base URL env: {base_url_env}\n"
        f"Default base URL: {default_base_url}\n"
        f"Suggested model: {default_model}"
    )


def _provider_menu_text() -> str:
    lines = ["Choose a model provider:\n"]
    for index, provider in enumerate(PROVIDERS, start=1):
        label = PROVIDER_LABELS[provider]
        model = DEFAULT_MODELS[provider]
        lines.append(f"{index}. {label} - default model: {model}")
    lines.append("")
    lines.append("Google/Gemini is planned later, but is not in this release yet.")
    return "\n".join(lines)


def _resolve_provider_choice(choice: str) -> str | None:
    normalized = choice.strip().lower()
    if normalized.isdigit():
        index = int(normalized)
        if 1 <= index <= len(PROVIDERS):
            return PROVIDERS[index - 1]
    for provider in PROVIDERS:
        if normalized in {provider, PROVIDER_LABELS[provider].lower()}:
            return provider
    return None


def _ask_provider() -> str:
    choices = [str(index) for index in range(1, len(PROVIDERS) + 1)]
    choices.extend(PROVIDERS)
    provider_choice = Prompt.ask("Provider number or name", choices=choices, default="1")
    provider = _resolve_provider_choice(provider_choice)
    if provider is None:
        raise RuntimeError(f"Unknown provider selection: {provider_choice}")
    return provider


def _hosted_base_url(provider: str) -> str:
    if provider == "custom":
        raise ValueError("Custom provider base URL must be entered by the user")
    return DEFAULT_BASE_URLS[provider]


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
                "Choose the provider you want the harness to call. Hosted\n"
                "providers only ask for an API key and model. Custom providers\n"
                "ask for a base URL first, then the API key.\n\n"
                "Provider keys:\n"
                "- OpenRouter: https://openrouter.ai/keys\n"
                "- OpenAI: https://platform.openai.com/api-keys\n"
                "- Anthropic: https://console.anthropic.com/settings/keys\n\n"
                "Secrets are written with private file permissions.",
                style="code",
            ),
            title=Text("Setup", style="bold cyan"),
            border_style="bright_cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )
    console.print()

    existing_files = _existing_setup_files(env_path, config_path)
    if existing_files:
        file_list = "\n".join(f"- {path}" for path in existing_files)
        console.print(
            Panel(
                Text(
                    "Existing AgentForge setup files were found:\n\n"
                    f"{file_list}\n\n"
                    "Continuing will overwrite these files.",
                    style="code",
                ),
                title=Text("Existing setup", style="bold yellow"),
                border_style="yellow",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )
        if not Confirm.ask("Overwrite existing setup files?", default=False):
            console.print("[warning]Setup cancelled. Existing files were left unchanged.[/warning]")
            return False

    console.print(
        Panel(
            Text(_provider_menu_text(), style="code"),
            title=Text("Provider", style="bold cyan"),
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )
    provider = _ask_provider()
    default_model = DEFAULT_MODELS[provider]

    console.print(
        Panel(
            Text(_provider_help(provider), style="code"),
            title=Text(f"{PROVIDER_LABELS[provider]} settings", style="bold cyan"),
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )

    if provider == "custom":
        base_url = Prompt.ask(
            "Base URL",
            default=DEFAULT_BASE_URLS[provider],
        ).strip()
        if not base_url:
            console.print("[error]Base URL is required for custom providers.[/error]")
            return False
    else:
        base_url = _hosted_base_url(provider)

    api_key = Prompt.ask("API key", password=True)
    if not api_key:
        console.print("[error]API key is required.[/error]")
        return False

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
                f"API key: configured\n"
                f"Base URL: {base_url or 'provider default'}\n"
                f"Model: {model}\n\n"
                "You can change these later by editing the file above,\n"
                "setting environment variables, or running agentforge init again.\n"
                "Run agentforge doctor next to verify the setup.",
                style="code",
            ),
            title=Text("Setup complete", style="bold green"),
            border_style="green",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )
    if Confirm.ask("Run local doctor check now?", default=True):
        from agentforge_harness.cli.doctor import build_doctor_report, print_doctor_report
        from agentforge_harness.config.loader import load_config

        try:
            print_doctor_report(build_doctor_report(load_config(Path.cwd())), console=console)
        except Exception as exc:
            console.print(f"[warning]Doctor check could not run: {exc}[/warning]")

    return True
