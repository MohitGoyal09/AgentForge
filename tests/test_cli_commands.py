from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agentforge_harness.agent.session import Session
from agentforge_harness.agent.persistence import PersistenceManager
from agentforge_harness.cli.models import ModelList, ModelOption
from agentforge_harness.cli.commands import CLI
from agentforge_harness.config.config import Config, ModelConfig, ModelProvider
from agentforge_harness.context.manager import ContextManager


def _capture_notices(cli: CLI) -> list[tuple[str, str | None]]:
    notices: list[tuple[str, str | None]] = []

    def show_notice(message: str, title: str | None = None) -> None:
        notices.append((message, title))

    cli.tui.show_notice = show_notice
    return notices


def _capture_models(cli: CLI) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def show_models(**kwargs: object) -> None:
        calls.append(kwargs)

    cli.tui.show_models = show_models
    return calls


async def test_model_command_without_argument_shows_current_model():
    cli = CLI(Config(cwd=Path("/tmp"), model=ModelConfig(name="test/original")))
    notices = _capture_notices(cli)

    assert await cli._handle_command("/model") is True

    assert notices
    assert "Current model: test/original" in notices[-1][0]
    assert "Usage: /model <model-id>" in notices[-1][0]


async def test_model_command_changes_config_without_active_agent():
    cli = CLI(Config(cwd=Path("/tmp"), model=ModelConfig(name="test/original")))
    notices = _capture_notices(cli)

    assert await cli._handle_command("/model openrouter/free") is True

    assert cli.config.model_name == "openrouter/free"
    assert "test/original -> openrouter/free" in notices[-1][0]


async def test_model_command_updates_active_session_state():
    config = Config(cwd=Path("/tmp"), model=ModelConfig(name="test/original"))
    cli = CLI(config)
    notices = _capture_notices(cli)
    session = Session(config)
    session.context_manager = ContextManager(
        config=config,
        tools=session.tool_registry.get_tools(mode=session.mode),
        skills=[],
        mode=session.mode,
    )
    for _ in range(session.circuit_breaker.failure_threshold):
        session.circuit_breaker.record_failure("openrouter/free")
    cli.agent = SimpleNamespace(session=session)

    assert await cli._handle_command("/model openrouter/free") is True

    assert cli.config.model_name == "openrouter/free"
    assert session.config.model_name == "openrouter/free"
    assert session.context_manager._model_name == "openrouter/free"
    assert session.circuit_breaker.is_open("openrouter/free") is False
    assert "This affects the current session" in notices[-1][0]


async def test_models_command_lists_models_for_current_provider(monkeypatch):
    cli = CLI(Config(cwd=Path("/tmp"), model=ModelConfig(name="openrouter/free")))
    calls = _capture_models(cli)

    async def fake_list_models(config: Config, limit: int = 24) -> ModelList:
        return ModelList(
            provider=config.provider.value,
            current_model=config.model_name,
            models=[ModelOption("openrouter/free", "current")],
            live=False,
            message="Curated suggestions",
        )

    monkeypatch.setattr("agentforge_harness.cli.command_registry.list_models_for_config", fake_list_models)

    assert await cli._handle_command("/models") is True

    assert calls
    assert calls[-1]["provider"] == "openrouter"
    assert calls[-1]["current_model"] == "openrouter/free"
    assert calls[-1]["models"] == [ModelOption("openrouter/free", "current")]


async def test_model_list_alias_lists_models(monkeypatch):
    cli = CLI(Config(cwd=Path("/tmp"), model=ModelConfig(name="openrouter/free")))
    calls = _capture_models(cli)

    async def fake_list_models(config: Config, limit: int = 24) -> ModelList:
        return ModelList(
            provider=config.provider.value,
            current_model=config.model_name,
            models=[ModelOption("openrouter/free", "current")],
            live=False,
        )

    monkeypatch.setattr("agentforge_harness.cli.command_registry.list_models_for_config", fake_list_models)

    assert await cli._handle_command("/model list") is True

    assert calls


async def test_provider_command_changes_runtime_provider_without_active_agent():
    cli = CLI(Config(cwd=Path("/tmp"), model=ModelConfig(name="openrouter/free")))

    assert await cli._handle_command("/provider openai gpt-4o-mini") is True

    assert cli.config.provider == ModelProvider.OPENAI
    assert cli.config.model_name == "gpt-4o-mini"
    assert cli.config.model.base_url is None


async def test_provider_command_requires_custom_base_url():
    cli = CLI(Config(cwd=Path("/tmp"), model=ModelConfig(name="openrouter/free")))
    errors: list[str] = []
    cli.tui.show_error = lambda message, title="Error": errors.append(message)

    assert await cli._handle_command("/provider custom") is True

    assert errors
    assert "Usage: /provider custom" in errors[-1]


async def test_fallbacks_command_adds_and_clears_models():
    cli = CLI(Config(cwd=Path("/tmp"), model=ModelConfig(name="openrouter/free")))

    assert await cli._handle_command("/fallbacks add meta/llama:free openai/gpt-4o-mini") is True
    assert cli.config.model.fallbacks == ["meta/llama:free", "openai/gpt-4o-mini"]

    assert await cli._handle_command("/fallbacks clear") is True
    assert cli.config.model.fallbacks == []


async def test_paths_command_shows_runtime_paths(tmp_path: Path):
    cli = CLI(Config(cwd=tmp_path, model=ModelConfig(name="openrouter/free")))
    calls: list[tuple[str, list[tuple[str, str]]]] = []
    cli.tui.show_key_values = lambda title, rows, **kwargs: calls.append((title, rows))

    assert await cli._handle_command("/paths") is True

    assert calls
    assert calls[-1][0] == "Paths"
    assert ("cwd", str(tmp_path)) in calls[-1][1]


async def test_errors_command_reads_recent_session_errors(tmp_path: Path):
    config = Config(cwd=tmp_path, model=ModelConfig(name="openrouter/free"))
    cli = CLI(config)
    rows_calls: list[list[tuple[str, str]]] = []
    cli.tui.show_key_values = lambda title, rows, **kwargs: rows_calls.append(rows)
    session = Session(config)
    cli.agent = SimpleNamespace(session=session)
    session.record_event("agent_error", {"error": "Rate limit exceeded"})

    assert await cli._handle_command("/errors") is True

    assert rows_calls
    assert "Rate limit exceeded" in rows_calls[-1][0][1]
