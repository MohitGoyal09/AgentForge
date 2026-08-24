from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastmcp.client.transports import SSETransport, StdioTransport, StreamableHttpTransport

from agentforge_harness.config.config import Config, MCPServerConfig
from agentforge_harness.tools.base import ToolInvocation
from agentforge_harness.tools.mcp.client import MCPClient, MCPServerStatus
from agentforge_harness.tools.mcp.mcp_manager import MCPManager
from agentforge_harness.tools.registry import ToolRegistry

PARALLEL_URL = "https://search.parallel.ai/mcp"


def _client(tmp_path: Path, **config) -> MCPClient:
    return MCPClient("server", MCPServerConfig(**config), tmp_path)


def test_parallel_uses_streamable_http_without_auth_or_headers(tmp_path: Path):
    transport = _client(tmp_path, url=PARALLEL_URL)._create_transport()
    assert isinstance(transport, StreamableHttpTransport)
    assert transport.url == PARALLEL_URL
    assert transport.headers == {}


def test_existing_transports_are_unchanged(tmp_path: Path):
    stdio = _client(tmp_path, command="server", args=["--flag"])._create_transport()
    sse = _client(tmp_path, url="https://example.test/sse")._create_transport()
    assert isinstance(stdio, StdioTransport)
    assert stdio.command == "server"
    assert stdio.args == ["--flag"]
    assert isinstance(sse, SSETransport)


async def test_call_tool_keeps_legacy_dict_for_all_transports(tmp_path: Path):
    result = SimpleNamespace(content=[SimpleNamespace(text="legacy text")], structured_content={"results": [{"title": "structured"}]}, is_error=False)
    for config in ({"command": "server"}, {"url": "https://example.test/sse"}, {"url": PARALLEL_URL}):
        client = _client(tmp_path, **config)
        client.status = MCPServerStatus.CONNECTED
        client._client = SimpleNamespace(call_tool=AsyncMock(return_value=result))
        actual = await client.call_tool("web_search", {"objective": "research"})
        assert set(actual) == {"output", "is_error"}
        assert actual["is_error"] is False
        if config.get("url") == PARALLEL_URL:
            assert json.loads(actual["output"]) == result.structured_content
        else:
            assert actual["output"] == "legacy text"


async def test_parallel_text_fallback_does_not_duplicate_structured_content(tmp_path: Path):
    client = _client(tmp_path, url=PARALLEL_URL)
    client.status = MCPServerStatus.CONNECTED
    client._client = SimpleNamespace(call_tool=AsyncMock(return_value=SimpleNamespace(content=[SimpleNamespace(text='{"results":[{"title":"text"}]}')], structured_content=None, is_error=False)))
    result = await client.call_tool("web_search", {})
    assert result == {"output": '{"results":[{"title":"text"}]}', "is_error": False}


async def test_manager_lists_and_calls_parallel_tool_with_hosted_schema(tmp_path: Path):
    schema = {"type": "object", "properties": {"objective": {"type": "string"}, "search_queries": {"type": "array", "items": {"type": "string"}}}, "required": ["objective", "search_queries"], "additionalProperties": False}
    remote = AsyncMock()
    remote.__aenter__.return_value = remote
    remote.list_tools.return_value = [SimpleNamespace(name="web_search", description="Search", inputSchema=schema)]
    remote.call_tool.return_value = SimpleNamespace(content=[SimpleNamespace(text="fallback")], structured_content={"results": [{"title": "answer"}]}, is_error=False)
    config = Config(cwd=tmp_path, mcp_servers={"parallel-search": MCPServerConfig(url=PARALLEL_URL)})
    manager = MCPManager(config)
    with patch("agentforge_harness.tools.mcp.client.Client", return_value=remote) as factory:
        await manager.initialize()
        registry = ToolRegistry(config)
        assert manager.register_tools(registry) == 1
        tool = registry.get("parallel-search__web_search")
        assert tool is not None
        assert tool.schema == schema
        arguments = {"objective": "Find current docs", "search_queries": ["AgentForge MCP"]}
        result = await tool.execute(ToolInvocation(params=arguments, cwd=tmp_path))
    assert isinstance(factory.call_args.kwargs["transport"], StreamableHttpTransport)
    assert result.success
    assert json.loads(result.output) == {"results": [{"title": "answer"}]}
    remote.call_tool.assert_awaited_once_with("web_search", arguments)
    assert "max_results" not in remote.call_tool.await_args.args[1]
