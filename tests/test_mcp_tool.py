"""Tests for MCPTool — covers BUG B (CallToolResult dataclass) and BUG G (ToolKind.MCP)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agentforge_harness.config.config import Config
from agentforge_harness.tools.base import ToolInvocation, ToolKind
from agentforge_harness.tools.mcp.mcp_tool import MCPTool


def _make_mcp_tool(tmp_path: Path, call_result: object) -> MCPTool:
    """Build an MCPTool with a fake client that returns *call_result*."""
    fake_client = AsyncMock()
    fake_client.call_tool = AsyncMock(return_value=call_result)

    fake_tool_info = SimpleNamespace(
        name="fake_mcp",
        description="A fake MCP tool",
        input_schema={"properties": {}, "required": []},
    )

    return MCPTool(
        config=Config(cwd=tmp_path),
        client=fake_client,
        tool_info=fake_tool_info,
        name="fake_mcp",
    )


def _invocation(tmp_path: Path) -> ToolInvocation:
    return ToolInvocation(params={}, cwd=tmp_path)


# ---------------------------------------------------------------------------
# BUG B — execute() must work with CallToolResult dataclass (not a dict)
# ---------------------------------------------------------------------------


async def test_execute_success_extracts_text_from_content_blocks(tmp_path: Path):
    """BUG B: content blocks with .text attribute are joined into the output."""
    call_result = SimpleNamespace(
        content=[SimpleNamespace(text="hi")],
        is_error=False,
        data=None,
        structured_content=None,
    )
    tool = _make_mcp_tool(tmp_path, call_result)

    result = await tool.execute(_invocation(tmp_path))

    assert result.success
    assert result.output == "hi"


async def test_execute_multiple_content_blocks_joined(tmp_path: Path):
    """Multiple text blocks are concatenated."""
    call_result = SimpleNamespace(
        content=[
            SimpleNamespace(text="hello "),
            SimpleNamespace(text="world"),
        ],
        is_error=False,
        data=None,
        structured_content=None,
    )
    tool = _make_mcp_tool(tmp_path, call_result)

    result = await tool.execute(_invocation(tmp_path))

    assert result.success
    assert result.output == "hello world"


async def test_execute_is_error_returns_error_result(tmp_path: Path):
    """BUG B: is_error=True on the dataclass must propagate to an error result."""
    call_result = SimpleNamespace(
        content=[SimpleNamespace(text="something went wrong")],
        is_error=True,
        data=None,
        structured_content=None,
    )
    tool = _make_mcp_tool(tmp_path, call_result)

    result = await tool.execute(_invocation(tmp_path))

    assert not result.success
    assert "something went wrong" in (result.error or result.output)


async def test_execute_falls_back_to_data_when_no_text_blocks(tmp_path: Path):
    """When content has no text blocks, fall back to the data attribute."""
    call_result = SimpleNamespace(
        content=[],
        is_error=False,
        data={"key": "value"},
        structured_content=None,
    )
    tool = _make_mcp_tool(tmp_path, call_result)

    result = await tool.execute(_invocation(tmp_path))

    assert result.success
    assert "key" in result.output or "value" in result.output


async def test_execute_exception_returns_error(tmp_path: Path):
    """Exceptions from the MCP client are caught and returned as an error."""
    fake_client = AsyncMock()
    fake_client.call_tool = AsyncMock(side_effect=RuntimeError("network failure"))

    fake_tool_info = SimpleNamespace(
        name="fail_mcp",
        description="fails",
        input_schema={"properties": {}, "required": []},
    )
    tool = MCPTool(
        config=Config(cwd=tmp_path),
        client=fake_client,
        tool_info=fake_tool_info,
        name="fail_mcp",
    )

    result = await tool.execute(_invocation(tmp_path))

    assert not result.success
    assert "network failure" in (result.error or "")


# ---------------------------------------------------------------------------
# BUG G — MCPTool.kind must be ToolKind.MCP (not READ)
# ---------------------------------------------------------------------------


def test_mcp_tool_kind_is_mcp(tmp_path: Path):
    """BUG G: MCPTool.kind must be ToolKind.MCP so PLAN mode excludes it."""
    call_result = SimpleNamespace(content=[], is_error=False, data=None, structured_content=None)
    tool = _make_mcp_tool(tmp_path, call_result)

    assert tool.kind == ToolKind.MCP


def test_mcp_tool_kind_is_not_read(tmp_path: Path):
    """PLAN mode filters to READ and NETWORK; MCP tools must not slip through."""
    call_result = SimpleNamespace(content=[], is_error=False, data=None, structured_content=None)
    tool = _make_mcp_tool(tmp_path, call_result)

    assert tool.kind != ToolKind.READ
