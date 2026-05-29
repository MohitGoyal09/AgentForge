from pydantic import BaseModel, Field

from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from utils.paths import is_binary_file, resolve_path
from utils.text import count_tokens, truncate_text


class ReadFileParams(BaseModel):

    path: str = Field(
        ...,
        description="Path to the file to read (relative to working directory or absolute)",
    )

    offset: int = Field(
        1,
        ge=1,
        description="Line number to start reading from (1-based). Defaults to 1",
    )

    limit: int | None = Field(
        None,
        ge=1,
        description="Maximum number of lines to read. If not specified, reads entire file.",
    )


class ReadFileTool(Tool):
    name = "read_file"
    description = (
        "Read the contents of a text file. Returns the file content with line numbers. "
        "Also reports whether the file has a trailing newline, which matters when creating patches. "
        "For large files, use offset and limit to read specific portions. "
        "Cannot read binary files (images, executables, etc.)."
    )
    kind = ToolKind.READ

    schema = ReadFileParams

    MAX_FILE_SIZE = 1024 * 1024 * 10
    MAX_OUTPUT_TOKENS = 25000

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = ReadFileParams(**invocation.params)
        path = resolve_path(invocation.cwd, params.path)

        if not path.exists():
            return ToolResult.error_result(
                f"File not found: {path}",
                summary=f"File not found: {path}",
                recovery_hint="Check the path with list_dir or glob, then retry read_file with the correct relative path.",
            )

        if not path.is_file():
            return ToolResult.error_result(
                f"Path is not a file: {path}",
                summary=f"Path is not a file: {path}",
                recovery_hint="Use list_dir for directories or provide a file path.",
            )

        file_size = path.stat().st_size

        if file_size > self.MAX_FILE_SIZE:
            return ToolResult.error_result(
                f"File too large ({file_size / (1024*1024):.1f}MB). "
                f"Maximum is {self.MAX_FILE_SIZE / (1024*1024):.0f}MB.",
                summary=f"File too large: {path} ({file_size / (1024*1024):.1f}MB)",
                recovery_hint="Use offset and limit parameters to read portions of the file, or use shell to read with head/tail.",
            )

        if is_binary_file(path):
            file_size_mb = file_size / (1024 * 1024)
            size_str = (
                f"{file_size_mb:.2f}MB" if file_size_mb >= 1 else f"{file_size} bytes"
            )
            return ToolResult.error_result(
                f"Cannot read binary file: {path.name} ({size_str}) "
                f"This tool only reads text files.",
                summary=f"Cannot read binary file: {path.name}",
                artifacts=[str(path)],
                recovery_hint="Use a binary-aware tool or inspect metadata instead of read_file.",
            )

        try:
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = path.read_text(encoding="latin-1")

            lines = content.splitlines()
            total_lines = len(lines)
            has_trailing_newline = content.endswith(("\n", "\r"))

            if total_lines == 0:
                return ToolResult.success_result(
                    "File is empty.",
                    summary=f"Read empty file: {path}",
                    artifacts=[str(path)],
                    metadata={
                        "lines": 0,
                        "has_trailing_newline": has_trailing_newline,
                    },
                )

            start_idx = max(0, params.offset - 1)

            if params.limit is not None:
                end_idx = min(start_idx + params.limit, total_lines)
            else:
                end_idx = total_lines

            selected_lines = lines[start_idx:end_idx]
            formatted_lines = []

            for i, line in enumerate(selected_lines, start=start_idx + 1):
                formatted_lines.append(f"{i:6}|{line}")

            output = "\n".join(formatted_lines)
            token_count = count_tokens(output)

            truncated = False
            if token_count > self.MAX_OUTPUT_TOKENS:
                output = truncate_text(
                    output,
                    self.config.model_name,
                    self.MAX_OUTPUT_TOKENS,
                    suffix=f"\n... [truncated {total_lines} total lines]",
                )
                truncated = True

            metadata_lines = []
            if start_idx > 0 or end_idx < total_lines:
                metadata_lines.append(
                    f"Showing lines {start_idx+1}-{end_idx} of {total_lines}"
                )
            if end_idx == total_lines and not has_trailing_newline:
                metadata_lines.append("No trailing newline at end of file")

            if metadata_lines:
                header = " | ".join(metadata_lines) + "\n\n"
                output = header + output

            return ToolResult.success_result(
                output=output,
                truncated=truncated,
                summary=f"Read lines {start_idx + 1}-{end_idx} of {path}",
                artifacts=[str(path)],
                next_actions=(
                    ["When patching this file, include no-final-newline handling if editing the last line."]
                    if end_idx == total_lines and not has_trailing_newline
                    else []
                ),
                metadata={
                    "path": str(path),
                    "total_lines": total_lines,
                    "shown_start": start_idx + 1,
                    "shown_end": end_idx,
                    "has_trailing_newline": has_trailing_newline,
                },
            )
        except Exception as e:
            return ToolResult.error_result(
                f"Failed to read file: {e}",
                summary=f"Failed to read file: {path}",
                recovery_hint="Check file permissions and encoding, then retry or use shell for deeper inspection.",
            )

        
        
