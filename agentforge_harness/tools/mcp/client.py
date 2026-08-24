import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any
from agentforge_harness.config.config import MCPServerConfig
from enum import Enum
from fastmcp import Client
from fastmcp.client.transports import (
    SSETransport,
    StdioTransport,
    StreamableHttpTransport,
)
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

PARALLEL_SEARCH_MCP_URL = "https://search.parallel.ai/mcp"


class MCPServerStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class MCPToolInfo:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    server_name: str = ""


class MCPClient:
    def __init__(self, name: str, config: MCPServerConfig, cwd: Path) -> None:
        self.name = name
        self.config = config
        self.cwd = cwd
        self.status = MCPServerStatus.DISCONNECTED
        self._client: Client | None = None

        self._tools: dict[str, MCPToolInfo] = dict()

    @property
    def tools(self) -> list[MCPToolInfo]:
        return list(self._tools.values())

    def _create_transport(
        self,
    ) -> StdioTransport | SSETransport | StreamableHttpTransport:
        if self.config.command:
            env = os.environ.copy()
            env.update(self.config.env)

            return StdioTransport(
                command=self.config.command,
                args=list(self.config.args),
                env=env,
                cwd=str(self.config.cwd or self.cwd),
                log_file=Path(os.devnull),
            )
        if self.config.url == PARALLEL_SEARCH_MCP_URL:
            return StreamableHttpTransport(url=self.config.url)

        return SSETransport(url=self.config.url)

    async def connect(self) -> None:
        if self.status == MCPServerStatus.CONNECTED:
            return
        self.status = MCPServerStatus.CONNECTING

        try:
            self._client = Client(transport=self._create_transport())

            await self._client.__aenter__()

            tool_result = await self._client.list_tools()
            for tool in tool_result:
                self._tools[tool.name] = MCPToolInfo(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=(
                        tool.inputSchema if hasattr(tool, "inputSchema") else {}
                    ),
                    server_name=self.name,
                )

            self.status = MCPServerStatus.CONNECTED

        except Exception:
            self.status = MCPServerStatus.ERROR
            raise

    async def reconnect(self, max_attempts: int = 3, base_delay: float = 1.0) -> bool:
        """Try to (re)connect with exponential backoff.

        Returns True if a connection was established, False otherwise.
        Does NOT raise on failure.
        """
        self._tools.clear()
        if self._client:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception:
                pass
            self._client = None
        self.status = MCPServerStatus.DISCONNECTED
        for attempt in range(max_attempts):
            logger.info(
                "MCP server %r reconnect attempt %d/%d",
                self.name,
                attempt + 1,
                max_attempts,
            )
            try:
                await self.connect()
                return True
            except Exception as exc:
                logger.warning(
                    "MCP server %r reconnect attempt %d failed: %s",
                    self.name,
                    attempt + 1,
                    exc,
                )
                if attempt < max_attempts - 1:
                    delay = base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
        return False

    async def disconnect(self) -> None:
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None

        self._tools.clear()
        self.status = MCPServerStatus.DISCONNECTED

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]):
        if not self._client or self.status != MCPServerStatus.CONNECTED:
            raise RuntimeError(f"Not connected to server {self.name}")

        result = await self._client.call_tool(tool_name, arguments)

        # Keep the long-standing public return contract for direct callers and
        # MCPTool. Parallel can repeat its JSON payload in both representations,
        # so prefer the structured form there and use text only as a fallback.
        structured = getattr(result, "structured_content", None)
        if self.config.url == PARALLEL_SEARCH_MCP_URL and structured is not None:
            output = json.dumps(structured)
        else:
            output_parts = []
            for item in result.content:
                if hasattr(item, "text"):
                    output_parts.append(item.text)
                else:
                    output_parts.append(str(item))
            output = "\n".join(output_parts)

        return {"output": output, "is_error": result.is_error}
