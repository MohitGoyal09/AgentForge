from __future__ import annotations

from pydantic import BaseModel, Field

from agentforge_harness.tools.base import Tool, ToolInvocation, ToolKind, ToolResult


class CountLinesParams(BaseModel):
    path: str = Field(..., description="Path to a text file inside the workspace.")


class CountLinesTool(Tool):
    name = "count_lines"
    description = "Count lines in a text file and return a structured observation."
    kind = ToolKind.READ
    schema = CountLinesParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = CountLinesParams(**invocation.params)
        path = (invocation.cwd / params.path).resolve()

        if not path.is_file():
            return ToolResult.error_result(
                f"File not found: {params.path}",
                summary="Could not count lines",
                recovery_hint="Use list_dir or glob to find the correct file, then retry.",
            )

        line_count = len(path.read_text(encoding="utf-8").splitlines())
        return ToolResult.success_result(
            f"{params.path}: {line_count} line(s)",
            summary=f"Counted {line_count} line(s) in {params.path}",
            artifacts=[str(path)],
            next_actions=["Use read_file if the exact contents are needed."],
            metadata={"path": str(path), "lines": line_count},
        )
