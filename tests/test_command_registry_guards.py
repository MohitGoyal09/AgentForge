"""Tests for context_manager=None guards in /stats and /report handlers."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

# Import the private handler functions directly
from agentforge_harness.cli.command_registry import _h_stats, _h_report


def _make_ctx(context_manager=None) -> MagicMock:
    """Build a minimal CommandContext mock with context_manager set."""
    session = MagicMock()
    session.context_manager = context_manager
    ctx = MagicMock()
    ctx.session = session
    return ctx


@pytest.mark.asyncio
async def test_stats_with_none_context_manager_returns_error():
    """/stats returns an error CommandResult when context_manager is None."""
    ctx = _make_ctx(context_manager=None)
    result = await _h_stats("", ctx)
    assert result.error is not None
    assert "context manager" in result.error.lower()


@pytest.mark.asyncio
async def test_stats_with_context_manager_calls_get_total_usage():
    """/stats proceeds normally when context_manager is not None."""
    cm = MagicMock()
    usage = MagicMock()
    usage.prompt_tokens = 10
    usage.completion_tokens = 5
    usage.total_tokens = 15
    usage.cached_tokens = 0
    cm.get_total_usage.return_value = usage

    ctx = _make_ctx(context_manager=cm)
    ctx.session._turn_count = 3
    ctx.session.mode.value = "build"
    ctx.session.tool_registry.get.return_value = None

    result = await _h_stats("", ctx)
    assert result.error is None
    cm.get_total_usage.assert_called_once()


@pytest.mark.asyncio
async def test_report_with_none_context_manager_returns_error():
    """/report returns an error CommandResult when context_manager is None."""
    ctx = _make_ctx(context_manager=None)
    result = await _h_report("", ctx)
    assert result.error is not None
    assert "context manager" in result.error.lower()


@pytest.mark.asyncio
async def test_report_with_no_session_returns_error():
    """/report returns an error when there is no active session."""
    ctx = MagicMock()
    ctx.session = None
    result = await _h_report("", ctx)
    assert result.error is not None
    assert "session" in result.error.lower()


@pytest.mark.asyncio
async def test_stats_with_no_session_returns_error():
    """/stats returns an error when there is no active session."""
    ctx = MagicMock()
    ctx.session = None
    result = await _h_stats("", ctx)
    assert result.error is not None
    assert "session" in result.error.lower()
