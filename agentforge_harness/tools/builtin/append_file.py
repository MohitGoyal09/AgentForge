from pydantic import BaseModel, Field

from agentforge_harness.tools.base import (
    FileDiff,
    Tool,
    ToolConfirmation,
    ToolInvocation,
    ToolKind,
    ToolResult,
)
from agentforge_harness.utils.paths import ensure_parent_directory, resolve_path


class AppendFileParams(BaseModel):
    path: str = Field(
        ...,
        description="Path to the file to append to, relative to the working directory or absolute.",
    )
    content: str = Field(
        ...,
        description="Text to append to the end of the file.",
    )
    ensure_newline_before: bool = Field(
        True,
        description="Insert a newline before appended content if the existing file does not end with one.",
    )
    ensure_trailing_newline: bool = Field(
        True,
        description="Ensure the resulting file ends with a newline.",
    )
    create_if_missing: bool = Field(
        True,
        description="Create the file and parent directories if the path does not exist.",
    )


class AppendFileTool(Tool):
    name = "append_file"
    description = (
        "Append text to the end of a file. Use this when the task is to add a "
        "section, notes, examples, or prose after existing content. This is safer "
        "and easier than apply_patch for simple append-only changes. For replacing "
        "existing text, use edit. For multi-file diffs, use apply_patch."
    )
    kind = ToolKind.WRITE
    schema = AppendFileParams

    def _build_new_content(self, old_content: str, append_content: str, params: AppendFileParams) -> str:
        content = append_content
        if old_content and params.ensure_newline_before and not old_content.endswith(("\n", "\r")):
            content = "\n" + content
        if params.ensure_trailing_newline and content and not content.endswith("\n"):
            content += "\n"
        return old_content + content

    async def get_confirmation(
        self,
        invocation: ToolInvocation,
    ) -> ToolConfirmation | None:
        params = AppendFileParams(**invocation.params)
        path = resolve_path(invocation.cwd, params.path)

        old_content = ""
        if path.exists():
            old_content = path.read_text(encoding="utf-8")

        new_content = self._build_new_content(old_content, params.content, params)

        return ToolConfirmation(
            tool_name=self.name,
            params=invocation.params,
            description=f"Append to file: {path}",
            diff=FileDiff(path=path, old_content=old_content, new_content=new_content, is_new_file=not path.exists()),
            affected_paths=[path],
        )

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = AppendFileParams(**invocation.params)
        path = resolve_path(invocation.cwd, params.path)

        if not path.exists() and not params.create_if_missing:
            return ToolResult.error_result(
                f"File does not exist: {path}",
                summary=f"Cannot append missing file: {path}",
                recovery_hint="Set create_if_missing=true or create the file with write_file first.",
            )

        try:
            existed = path.exists()
            old_content = path.read_text(encoding="utf-8") if existed else ""
            new_content = self._build_new_content(old_content, params.content, params)

            ensure_parent_directory(path)
            path.write_text(new_content, encoding="utf-8")

            appended_lines = len(params.content.splitlines())
            return ToolResult.success_result(
                f"Appended {appended_lines} line(s) to {path}",
                summary=f"Appended text to {path}",
                artifacts=[str(path)],
                next_actions=["Use read_file to verify the appended content if needed."],
                diff_text=FileDiff(
                    path=path,
                    old_content=old_content,
                    new_content=new_content,
                    is_new_file=not existed,
                ).to_diff(),
                metadata={
                    "path": str(path),
                    "appended_lines": appended_lines,
                    "bytes_added": len((new_content[len(old_content) :]).encode("utf-8")),
                    "created": not existed,
                },
            )
        except OSError as e:
            return ToolResult.error_result(
                f"Failed to append file: {e}",
                summary=f"Failed to append file: {path}",
                artifacts=[str(path)],
                recovery_hint="Check file permissions and parent directory state before retrying.",
            )
