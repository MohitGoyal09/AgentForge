import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from agentforge_harness.tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field


class WebFetchParams(BaseModel):
    url: str = Field(..., description="URL to fetch (must be http:// or https://)")
    timeout: int = Field(
        30,
        ge=5,
        le=120,
        description="Request timeout in seconds (default: 120)",
    )


def _is_private_host(hostname: str) -> tuple[bool, str]:
    """Return (is_blocked, reason).

    BUG H fix: resolve the hostname and reject private/loopback/link-local/
    reserved/multicast addresses to prevent SSRF against internal services
    (e.g. cloud metadata endpoints, 127.0.0.1, 10.x/172.16-31.x/192.168.x).
    """
    try:
        results = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        # DNS resolution failed — let the request fail naturally.
        return False, ""

    for _family, _type, _proto, _canonname, sockaddr in results:
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
        ):
            return True, ip_str
    return False, ""


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Fetch content from a URL. Returns the response body as text"
    kind = ToolKind.NETWORK
    schema = WebFetchParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = WebFetchParams(**invocation.params)

        parsed = urlparse(params.url)
        if not parsed.scheme or parsed.scheme not in ("http", "https"):
            return ToolResult.error_result(
                "URL must be http:// or https://",
                summary=f"Invalid URL scheme: {params.url}",
                recovery_hint="Ensure the URL starts with http:// or https://, then retry.",
            )

        # BUG H fix: block requests to private/loopback/link-local/reserved hosts.
        hostname = parsed.hostname or ""
        if hostname:
            blocked, resolved_ip = _is_private_host(hostname)
            if blocked:
                return ToolResult.error_result(
                    f"Blocked: {hostname} resolves to a private/reserved address ({resolved_ip})",
                    summary=f"SSRF protection blocked request to {params.url}",
                    recovery_hint="Only public internet URLs are allowed.",
                )

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
            next_actions=["Review the fetched content. Use grep or read_file on local files for further analysis."],
            artifacts=[params.url],
            metadata={
                "status_code": response.status_code,
                "content_length": len(response.content),
            },
        )   