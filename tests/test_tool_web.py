from __future__ import annotations

import pytest
from pydantic_core import ValidationError
from tools.base import ToolInvocation


class TestWebSearchTool:
    async def test_empty_query_returns_error(self, web_search_tool, invocation):
        result = await web_search_tool.execute(
            ToolInvocation(params={"query": ""}, cwd=invocation.cwd)
        )
        assert not result.success

    async def test_max_results_in_metadata(self, web_search_tool, invocation):
        result = await web_search_tool.execute(
            ToolInvocation(params={"query": "test"}, cwd=invocation.cwd)
        )
        assert result.metadata.get("results") == 10

    async def test_recovery_hint_on_failure(self, web_search_tool, invocation):
        result = await web_search_tool.execute(
            ToolInvocation(params={"query": ""}, cwd=invocation.cwd)
        )
        assert result.recovery_hint

    async def test_next_actions_on_success(self, web_search_tool, invocation):
        result = await web_search_tool.execute(
            ToolInvocation(params={"query": "python"}, cwd=invocation.cwd)
        )
        assert result.next_actions


class TestWebFetchTool:
    async def test_invalid_url_returns_error(self, web_fetch_tool, invocation):
        result = await web_fetch_tool.execute(
            ToolInvocation(params={"url": "not-a-url"}, cwd=invocation.cwd)
        )
        assert not result.success
        assert "http" in result.error.lower()

    async def test_empty_url_returns_error(self, web_fetch_tool, invocation):
        result = await web_fetch_tool.execute(
            ToolInvocation(params={"url": ""}, cwd=invocation.cwd)
        )
        assert not result.success

    async def test_recovery_hint_on_invalid_url(self, web_fetch_tool, invocation):
        result = await web_fetch_tool.execute(
            ToolInvocation(params={"url": "ftp://bad"}, cwd=invocation.cwd)
        )
        assert result.recovery_hint

    async def test_timeout_validation_at_pydantic_level(self):
        with pytest.raises(ValidationError, match="timeout"):
            from tools.builtin.web_fetch import WebFetchParams
            WebFetchParams(url="https://example.com", timeout=3)

    async def test_recovery_hint_on_network_error(self, web_fetch_tool, invocation):
        result = await web_fetch_tool.execute(
            ToolInvocation(params={"url": "https://nonexistent.invalid"}, cwd=invocation.cwd)
        )
        assert result.recovery_hint
