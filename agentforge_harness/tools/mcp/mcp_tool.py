from typing import Any
from fastmcp.client import Client
from agentforge_harness.config.config import Config
from agentforge_harness.tools.base import Tool, ToolInvocation, ToolKind, ToolResult


from agentforge_harness.tools.mcp.client import MCPToolInfo




class MCPTool(Tool):
    # BUG G fix: MCP tools must not appear in PLAN mode (which only allows READ/NETWORK).
    kind: ToolKind = ToolKind.MCP

    def __init__(
        self ,
        config : Config ,
        client : Client,
        tool_info : MCPToolInfo ,
        name : str) -> None:

        super().__init__(config)
        self._tool_info = tool_info
        self._client = client
        self.name = name
        self.description = self._tool_info.description


    @property
    def schema(self) -> dict[str, Any]:
        input_schema = self._tool_info.input_schema or {}
        schema = {
            'type' : 'object',
            'properties' : input_schema.get('properties' , {}),
            'required' : input_schema.get('required' , []),
        }
        if 'additionalProperties' in input_schema:
            schema['additionalProperties'] = input_schema['additionalProperties']
        return schema


    def is_mutating(self, params) -> bool:
        return True

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        try :
            result = await self._client.call_tool(
                self._tool_info.name,
                invocation.params,
            )
            if isinstance(result, dict):
                # MCPClient has always exposed this small dictionary contract.
                output = str(result.get("output", ""))
                is_error = bool(result.get("is_error", False))
            else:
                # Retain compatibility with custom clients returning FastMCP's
                # CallToolResult directly.
                content_blocks = getattr(result, "content", None) or []
                text_parts = [
                    getattr(block, "text", "")
                    for block in content_blocks
                    if hasattr(block, "text")
                ]
                if text_parts:
                    output = "".join(text_parts)
                else:
                    data = getattr(result, "data", None)
                    structured = getattr(result, "structured_content", None)
                    output = (
                        str(data)
                        if data is not None
                        else str(structured) if structured is not None else ""
                    )
                is_error = bool(getattr(result, "is_error", False))


            if is_error:
                return ToolResult.error_result(output)
            return ToolResult.success_result(output)
        except Exception as e:
            return ToolResult.error_result(f'MCP tool failed: {e}' )