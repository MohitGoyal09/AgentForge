from urllib.parse import urlparse

import httpx
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field


class WebFetchParams(BaseModel):
    url: str = Field(..., description="URL to fetch (must be http:// or https://)")
    timeout: int = Field(
        30,
        ge=5,
        le=120,
        description="Request timeout in seconds (default: 120)",
    )


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Fetch content from a URL. Returns the response body as text"
    kind = ToolKind.NETWORK
    schema = WebFetchParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = WebFetchParams(**invocation.params)

        parsed = urlparse(params.url)
        if not parsed.scheme or parsed.scheme not in ("http", "https"):
            return ToolResult.error_result("URL must be http:// or https://")

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(params.timeout),
                follow_redirects=True,
            ) as client:
                response = await client.get(params.url)
                response.raise_for_status()
                text = response.text
        except httpx.HTTPStatusError as e:
            return ToolResult.error_result(
                f"HTTP {e.response.status_code}: {e.response.reason_phrase}",
                summary=f"HTTP {e.response.status_code} fetching {params.url}",
                recovery_hint="Check the URL for typos. If the site requires authentication, this tool may not work.",
            )
        except Exception as e:
            return ToolResult.error_result(
                f"Request failed: {e}",
                summary=f"Failed to fetch {params.url}",
                recovery_hint="Verify the URL is reachable and the network is available.",
            )

        if len(text) > 100 * 1024:
            text = text[: 100 * 1024] + "\n... [content truncated]"

        return ToolResult.success_result(
            text,
            summary=f"Fetched {params.url} ({len(response.content)} bytes)",
            artifacts=[params.url],
            metadata={
                "status_code": response.status_code,
                "content_length": len(response.content),
            },
        )   