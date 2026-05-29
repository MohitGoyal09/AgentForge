from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field

from utils.paths import resolve_path


class ListDirParams(BaseModel):
    path: str = Field(
        ".", description="Directory path to list (default: current directory)"
    )
    include_hidden: bool = Field(
        False,
        description="Whether to include hidden files and directories (default: false",
    )


class ListDirTool(Tool):
    name = "list_dir"
    description = "List contents of a directory"
    kind = ToolKind.READ
    schema = ListDirParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = ListDirParams(**invocation.params)

        dir_path = resolve_path(invocation.cwd, params.path)

        if not dir_path.exists() or not dir_path.is_dir():
            return ToolResult.error_result(
                f"Directory does not exist: {dir_path}",
                summary=f"Directory not found: {dir_path}",
                recovery_hint="Check the path with glob, then retry with a valid directory path.",
            )

        try:
            items = sorted(
                dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())
            )
        except Exception as e:
            return ToolResult.error_result(
                f"Error listing directory: {e}",
                summary=f"Failed to list: {dir_path}",
                recovery_hint="Check directory permissions and existence, then retry.",
            )

        if not params.include_hidden:
            items = [item for item in items if not item.name.startswith(".")]

        if not items:
            return ToolResult.success_result(
                "Directory is empty",
                summary=f"Empty directory: {dir_path}",
                artifacts=[str(dir_path)],
                metadata={"path": str(dir_path), "entries": 0},
            )

        lines = []
        entry_paths = []

        for item in items:
            if item.is_dir():
                lines.append(f"{item.name}/")
            else:
                lines.append(item.name)
            entry_paths.append(str(item))

        return ToolResult.success_result(
            "\n".join(lines),
            summary=f"Listed {len(items)} entries in {dir_path}",
            next_actions=["Use read_file on specific files to inspect their contents."],
            artifacts=[str(dir_path)],
            metadata={
                "path": str(dir_path),
                "entries": len(items),
            },
        )
