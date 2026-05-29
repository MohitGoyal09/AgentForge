import re
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field

from utils.paths import find_source_files, resolve_path


class GrepParams(BaseModel):
    pattern: str = Field(..., description="Regular expression pattern to search for")
    path: str = Field(
        ".", description="File or directory to search in (default: current directory)"
    )
    case_insensitive: bool = Field(
        False,
        description="Case-insensitive search (default: false)",
    )


class GrepTool(Tool):
    name = "grep"
    description = "Search for a regex pattern in file contents. Returns matching lines with file paths and line numbers."
    kind = ToolKind.READ
    schema = GrepParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = GrepParams(**invocation.params)

        search_path = resolve_path(invocation.cwd, params.path)

        if not search_path.exists():
            return ToolResult.error_result(
                f"Path does not exist: {search_path}",
                summary=f"Path not found: {search_path}",
                recovery_hint="Verify the path with glob or list_dir, then retry.",
            )

        try:
            flags = re.IGNORECASE if params.case_insensitive else 0
            pattern = re.compile(params.pattern, flags)
        except re.error as e:
            return ToolResult.error_result(
                f"Invalid regex pattern: {e}",
                summary="Invalid regex pattern",
                recovery_hint="Fix the regex syntax and retry. Use a simpler pattern if unsure.",
            )

        if search_path.is_dir():
            files = find_source_files(search_path)
        else:
            files = [search_path]

        output_lines = []
        matches = 0
        matched_file_paths: list[str] = []

        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception:
                continue

            lines = content.splitlines()
            file_matches = False

            for i, line in enumerate(lines, start=1):
                if pattern.search(line):
                    matches += 1
                    if not file_matches:
                        rel_path = file_path.relative_to(invocation.cwd)
                        output_lines.append(f"=== {rel_path} ===")
                        file_matches = True

                    output_lines.append(f"{i}:{line}")

            if file_matches:
                output_lines.append("")
                matched_file_paths.append(str(file_path))

        if not output_lines:
            return ToolResult.success_result(
                f"No matches found for pattern '{params.pattern}'",
                summary=f"No matches for '{params.pattern}' in {search_path}",
                metadata={
                    "path": str(search_path),
                    "matches": 0,
                    "files_searched": len(files),
                },
            )

        return ToolResult.success_result(
            "\n".join(output_lines),
            summary=f"Found {matches} match(es) in {len(matched_file_paths)} file(s) for '{params.pattern}'",
            next_actions=["Use read_file on matching files to inspect full context."],
            artifacts=matched_file_paths[:20],
            metadata={
                "path": str(search_path),
                "matches": matches,
                "files_searched": len(files),
            },
        )

