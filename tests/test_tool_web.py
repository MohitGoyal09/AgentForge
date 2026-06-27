from __future__ import annotations

import pytest
from pydantic_core import ValidationError
from agentforge_harness.tools.base import ToolInvocation


class FakeDDGS:
    def text(self, *args, **kwargs):
        return [
            {
                "title": f"Result {index}",
                "href": f"https://example.com/{index}",
                "body": f"Snippet {index}",
            }
            for index in range(1, 21)
        ]


class TestWebSearchTool:
    async def test_empty_query_returns_error(self, web_search_tool, invocation):
        result = await web_search_tool.execute(
            ToolInvocation(params={"query": ""}, cwd=invocation.cwd)
        )
        assert not result.success

    async def test_max_results_in_metadata(self, web_search_tool, invocation, monkeypatch):
        monkeypatch.setattr("agentforge_harness.tools.builtin.web_search.DDGS", lambda: FakeDDGS())
        result = await web_search_tool.execute(
            ToolInvocation(params={"query": "test"}, cwd=invocation.cwd)
        )
        assert result.metadata.get("results") == 10

    async def test_recovery_hint_on_failure(self, web_search_tool, invocation):
        result = await web_search_tool.execute(
            ToolInvocation(params={"query": ""}, cwd=invocation.cwd)
        )
        assert result.recovery_hint

    async def test_next_actions_on_success(self, web_search_tool, invocation, monkeypatch):
        monkeypatch.setattr("agentforge_harness.tools.builtin.web_search.DDGS", lambda: FakeDDGS())
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
            from agentforge_harness.tools.builtin.web_fetch import WebFetchParams
            WebFetchParams(url="https://example.com", timeout=3)

    async def test_recovery_hint_on_network_error(self, web_fetch_tool, invocation):
        result = await web_fetch_tool.execute(
            ToolInvocation(params={"url": "https://nonexistent.invalid"}, cwd=invocation.cwd)
        )
        assert result.recovery_hint

    # ------------------------------------------------------------------
    # BUG H — SSRF: private/loopback addresses must be blocked
    # ------------------------------------------------------------------

    async def test_loopback_address_is_blocked(self, web_fetch_tool, invocation):
        """BUG H: requests to 127.0.0.1 must return an error, not make a connection."""
        result = await web_fetch_tool.execute(
            ToolInvocation(params={"url": "http://127.0.0.1/"}, cwd=invocation.cwd)
        )
        assert not result.success
        error_text = (result.error or "") + result.output
        assert any(
            kw in error_text.lower() for kw in ("blocked", "private", "reserved", "forbidden", "ssrf")
        )

    async def test_cloud_metadata_endpoint_is_blocked(self, web_fetch_tool, invocation):
        """BUG H: the AWS/GCP/Azure metadata endpoint 169.254.169.254 is link-local
        and must be blocked."""
        result = await web_fetch_tool.execute(
            ToolInvocation(
                params={"url": "http://169.254.169.254/"}, cwd=invocation.cwd
            )
        )
        assert not result.success
        error_text = (result.error or "") + result.output
        assert any(
            kw in error_text.lower() for kw in ("blocked", "private", "reserved", "forbidden", "ssrf", "link-local", "link_local")
        )

    async def test_private_class_a_network_is_blocked(self, web_fetch_tool, invocation):
        """10.x.x.x is a private RFC-1918 range and must be blocked."""
        result = await web_fetch_tool.execute(
            ToolInvocation(params={"url": "http://10.0.0.1/"}, cwd=invocation.cwd)
        )
        assert not result.success

    async def test_localhost_hostname_is_blocked(self, web_fetch_tool, invocation):
        """'localhost' resolves to 127.0.0.1 which is loopback and must be blocked."""
        result = await web_fetch_tool.execute(
            ToolInvocation(params={"url": "http://localhost/"}, cwd=invocation.cwd)
        )
        assert not result.success
