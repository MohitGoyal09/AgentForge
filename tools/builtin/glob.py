from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field

from utils.paths import resolve_path


class GlobParams(BaseModel):
    pattern: str = Field(..., description="Glob pattern to match")
    path: str = Field(
        ".", description="Directory to search in (default: current directory)"
    )


class GlobTool(Tool):
    name = "glob"
    description = (
        "Find files matching a glob pattern. Supports ** for recursive matching."
    )
    kind = ToolKind.READ
    schema = GlobParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = GlobParams(**invocation.params)

        search_path = resolve_path(invocation.cwd, params.path)

        if not search_path.exists() or not search_path.is_dir():
            return ToolResult.error_result(
                f"Directory does not exist: {search_path}",
                summary=f"Directory not found: {search_path}",
                recovery_hint="Verify the directory path with list_dir, then retry with a valid path.",
            )

        try:
            matches = list(search_path.glob(params.pattern))
            matches = [p for p in matches if p.is_file()]
        except Exception as e:
            return ToolResult.error_result(
                f"Error searching: {e}",
                summary="Glob pattern error",
                recovery_hint="Check the glob pattern syntax and directory path, then retry.",
            )

        output_lines = []
        matched_paths = []

        for file_path in matches[:1000]:
            try:
                rel_path = file_path.relative_to(invocation.cwd)
            except Exception:
                rel_path = file_path

            output_lines.append(str(rel_path))
            matched_paths.append(str(rel_path))

        if len(matches) > 1000:
            output_lines.append(f"...(limited to 1000 results)")

        return ToolResult.success_result(
            "\n".join(output_lines),
            summary=f"Found {len(matches)} file(s) matching {params.pattern}",
            next_actions=["Use read_file to inspect specific files, or grep to search within them."],
            artifacts=matched_paths[:50],
            metadata={
                "path": str(search_path),
                "matches": len(matches),
            },
        )