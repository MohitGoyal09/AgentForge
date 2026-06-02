from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agentforge_harness.agent.session import Session
from agentforge_harness.cli.commands import CLI
from agentforge_harness.config.config import Config, ModelConfig
from agentforge_harness.context.manager import ContextManager


def _capture_notices(cli: CLI) -> list[tuple[str, str | None]]:
    notices: list[tuple[str, str | None]] = []

    def show_notice(message: str, title: str | None = None) -> None:
        notices.append((message, title))

    cli.tui.show_notice = show_notice
    return notices


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
