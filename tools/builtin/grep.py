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
    context: int = Field(
        0, ge=0, le=50,
        description="Number of lines of context to show before and after each match (default: 0). "
                    "Like grep -C. Useful for understanding code around matches.",
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

        ctx = params.context

        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception:
                continue

            file_lines = content.splitlines()
            file_matches = False
            matched_line_numbers: set[int] = set()

            for i, line in enumerate(file_lines, start=1):
                if pattern.search(line):
                    matches += 1
                    matched_line_numbers.add(i)
                    if not file_matches:
                        rel_path = file_path.relative_to(invocation.cwd)
                        output_lines.append(f"=== {rel_path} ===")
                        file_matches = True

            if not file_matches:
                continue

            if ctx:
                context_lines: set[int] = set()
                for ln in matched_line_numbers:
                    for offset in range(-ctx, ctx + 1):
                        context_lines.add(ln + offset)
                context_lines = {ln for ln in context_lines if 1 <= ln <= len(file_lines)}
                prev_was_gap = False
                for ln in sorted(context_lines):
                    if ln not in matched_line_numbers and ln - 1 not in context_lines:
                        if not prev_was_gap:
                            output_lines.append("...")
                            prev_was_gap = True
                        continue
                    prev_was_gap = False
                    prefix = "> " if ln in matched_line_numbers else "  "
                    output_lines.append(f"{prefix}{ln}:{file_lines[ln - 1]}")
            else:
                for i, line in enumerate(file_lines, start=1):
                    if i in matched_line_numbers:
                        output_lines.append(f"{i}:{line}")

            output_lines.append("")
            matched_file_paths.append(str(file_path))

        if not output_lines:
            return ToolResult.success_result(
                f"No matches found for pattern '{params.pattern}'",
                summary=f"No matches for '{params.pattern}' in {search_path}",
                next_actions=["Try a broader pattern, a case-insensitive search, or remove path filters."],
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

