"""Tests for P2.3b — CommandRegistry / CommandResult / Session.handle_command."""
from __future__ import annotations

from pathlib import Path

import pytest

from agentforge_harness.agent.persistence import PersistenceManager
from agentforge_harness.agent.session import Session
from agentforge_harness.cli.command_registry import CommandContext, build_registry, get_registry
from agentforge_harness.cli.command_result import CommandResult
from agentforge_harness.config.config import Config, ModelConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(tmp_path: Path, session=None) -> CommandContext:
    config = Config(cwd=tmp_path, model_name="test/model")
    return CommandContext(session=session, config=config, agent=None)


async def _make_session(tmp_path: Path) -> Session:
    config = Config(cwd=tmp_path, model_name="test/model")
    session = Session(config=config, persistence=PersistenceManager(data_dir=tmp_path))
    await session.initialize()
    return session


# ---------------------------------------------------------------------------
# CommandResult defaults
# ---------------------------------------------------------------------------


def test_command_result_defaults():
    r = CommandResult()
    assert r.handled is True
    assert r.exit is False
    assert r.clear is False
    assert r.compact is False
    assert r.switch_mode is None
    assert r.retry is False
    assert r.notice is None
    assert r.error is None
    assert r.data_type is None
    assert r.data is None


# ---------------------------------------------------------------------------
# Registry dispatch — unknown command
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registry_returns_not_handled_for_unknown_command(tmp_path):
    registry = build_registry()
    ctx = _ctx(tmp_path)
    result = await registry.dispatch("/nonexistent_command_xyz", "", ctx)
    assert result.handled is False


# ---------------------------------------------------------------------------
# /exit → exit=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exit_command_returns_exit(tmp_path):
    registry = build_registry()
    ctx = _ctx(tmp_path)
    result = await registry.dispatch("/exit", "", ctx)
    assert result.exit is True
    assert result.handled is True


@pytest.mark.asyncio
async def test_quit_alias_for_exit(tmp_path):
    registry = build_registry()
    ctx = _ctx(tmp_path)
    result = await registry.dispatch("/quit", "", ctx)
    assert result.exit is True


# ---------------------------------------------------------------------------
# /help → data_type="help"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_help_command(tmp_path):
    registry = build_registry()
    result = await registry.dispatch("/help", "", _ctx(tmp_path))
    assert result.data_type == "help"
    assert result.handled is True


# ---------------------------------------------------------------------------
# /clear → clear=True + notice
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_clears_context_manager(tmp_path):
    session = await _make_session(tmp_path)
    session.context_manager.add_user_message("hello")
    assert len(session.context_manager._messages) == 1

    registry = build_registry()
    config = Config(cwd=tmp_path, model_name="test/model")
    ctx = CommandContext(session=session, config=config, agent=None)
    result = await registry.dispatch("/clear", "", ctx)

    assert result.clear is True
    assert result.notice is not None
    assert len(session.context_manager._messages) == 0


# ---------------------------------------------------------------------------
# /model — no arg shows current; with arg changes model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_model_no_arg_shows_current(tmp_path):
    registry = build_registry()
    config = Config(cwd=tmp_path, model=ModelConfig(name="test/original"))
    ctx = CommandContext(session=None, config=config, agent=None)
    result = await registry.dispatch("/model", "", ctx)
    assert result.notice is not None
    assert "test/original" in result.notice


@pytest.mark.asyncio
async def test_model_with_arg_updates_config(tmp_path):
    registry = build_registry()
    config = Config(cwd=tmp_path, model=ModelConfig(name="test/original"))
    ctx = CommandContext(session=None, config=config, agent=None)
    result = await registry.dispatch("/model", "new/model", ctx)
    assert result.notice is not None
    assert config.model_name == "new/model"


# ---------------------------------------------------------------------------
# /plan and /build → switch_mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_command_sets_switch_mode(tmp_path):
    session = await _make_session(tmp_path)
    config = Config(cwd=tmp_path, model_name="test/model")
    ctx = CommandContext(session=session, config=config, agent=None)
    result = await get_registry().dispatch("/plan", "", ctx)
    assert result.switch_mode == "plan"
    from agentforge_harness.agent.modes import AgentMode
    assert session.mode == AgentMode.PLAN


@pytest.mark.asyncio
async def test_build_command_sets_switch_mode(tmp_path):
    session = await _make_session(tmp_path)
    config = Config(cwd=tmp_path, model_name="test/model")
    ctx = CommandContext(session=session, config=config, agent=None)
    result = await get_registry().dispatch("/build", "", ctx)
    assert result.switch_mode == "build"
    from agentforge_harness.agent.modes import AgentMode
    assert session.mode == AgentMode.BUILD


# ---------------------------------------------------------------------------
# /new → calls session.reset() + clear=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_command_resets_session(tmp_path):
    session = await _make_session(tmp_path)
    session.context_manager.add_user_message("test message")
    original_id = session.session_id

    config = Config(cwd=tmp_path, model_name="test/model")
    ctx = CommandContext(session=session, config=config, agent=None)
    result = await get_registry().dispatch("/new", "", ctx)

    assert result.clear is True
    assert result.notice is not None
    assert session.session_id != original_id  # reset generates new id


# ---------------------------------------------------------------------------
# /thinking — no arg shows level; with arg updates it
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_thinking_no_arg_shows_level(tmp_path):
    config = Config(cwd=tmp_path, model_name="test/model")
    ctx = CommandContext(session=None, config=config, agent=None)
    result = await get_registry().dispatch("/thinking", "", ctx)
    assert result.notice is not None
    assert "thinking level" in result.notice.lower()


@pytest.mark.asyncio
async def test_thinking_invalid_level_returns_error(tmp_path):
    config = Config(cwd=tmp_path, model_name="test/model")
    ctx = CommandContext(session=None, config=config, agent=None)
    result = await get_registry().dispatch("/thinking", "invalid_level_xyz", ctx)
    assert result.error is not None


# ---------------------------------------------------------------------------
# /approval — no session needed for show; unknown level → error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approval_unknown_returns_error(tmp_path):
    config = Config(cwd=tmp_path, model_name="test/model")
    ctx = CommandContext(session=None, config=config, agent=None)
    result = await get_registry().dispatch("/approval", "invalid_policy", ctx)
    assert result.error is not None


# ---------------------------------------------------------------------------
# /stats and /tools require an active session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_requires_session(tmp_path):
    config = Config(cwd=tmp_path, model_name="test/model")
    ctx = CommandContext(session=None, config=config, agent=None)
    result = await get_registry().dispatch("/stats", "", ctx)
    assert result.error is not None


@pytest.mark.asyncio
async def test_stats_with_session_returns_data(tmp_path):
    session = await _make_session(tmp_path)
    config = Config(cwd=tmp_path, model_name="test/model")
    ctx = CommandContext(session=session, config=config, agent=None)
    result = await get_registry().dispatch("/stats", "", ctx)
    assert result.data_type == "stats"
    assert "turns" in result.data


# ---------------------------------------------------------------------------
# Session.handle_command integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_handle_command_dispatches_help(tmp_path):
    session = await _make_session(tmp_path)
    result = await session.handle_command("/help")
    assert result.handled is True
    assert result.data_type == "help"


@pytest.mark.asyncio
async def test_session_handle_command_unknown_returns_not_handled(tmp_path):
    session = await _make_session(tmp_path)
    result = await session.handle_command("/totally_unknown_cmd")
    assert result.handled is False


@pytest.mark.asyncio
async def test_session_handle_command_not_a_command_returns_error(tmp_path):
    session = await _make_session(tmp_path)
    result = await session.handle_command("hello world")
    assert result.handled is False
    assert result.error is not None


@pytest.mark.asyncio
async def test_session_handle_command_plan_switches_mode(tmp_path):
    session = await _make_session(tmp_path)
    result = await session.handle_command("/plan")
    assert result.switch_mode == "plan"
    from agentforge_harness.agent.modes import AgentMode
    assert session.mode == AgentMode.PLAN


# ---------------------------------------------------------------------------
# known_commands contains all expected commands
# ---------------------------------------------------------------------------


def test_registry_known_commands_complete():
    registry = build_registry()
    known = set(registry.known_commands)
    required = {
        "/exit", "/quit", "/help", "/clear", "/config", "/doctor", "/provider",
        "/model", "/models", "/fallbacks", "/paths", "/compact", "/errors",
        "/approval", "/thinking", "/tools", "/skills", "/skill", "/unskill",
        "/mcp", "/name", "/save", "/sessions", "/resume", "/checkpoint",
        "/checkpoints", "/restore", "/new", "/reload", "/version", "/retry",
        "/history", "/report", "/plan", "/build", "/todos", "/stats",
        "/export", "/branch", "/rewind",
    }
    missing = required - known
    assert not missing, f"Commands missing from registry: {missing}"
