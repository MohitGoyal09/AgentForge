from agentforge_harness.tools.builtin.append_file import AppendFileTool
from agentforge_harness.tools.builtin.edit_file import EditTool
from agentforge_harness.tools.builtin.glob import GlobTool
from agentforge_harness.tools.builtin.grep import GrepTool
from agentforge_harness.tools.builtin.list_dir import ListDirTool
from agentforge_harness.tools.builtin.memory import MemoryTool
from agentforge_harness.tools.builtin.patch import ApplyPatchTool
from agentforge_harness.tools.builtin.read_file import ReadFileTool
from agentforge_harness.tools.builtin.shell import ShellTool
from agentforge_harness.tools.builtin.todo import TodosTool
from agentforge_harness.tools.builtin.web_fetch import WebFetchTool
from agentforge_harness.tools.builtin.web_search import WebSearchTool
from agentforge_harness.tools.builtin.write_file import WriteFileTool

__all__ = [
    "ReadFileTool",
    "WriteFileTool",
    "AppendFileTool",
    "EditTool",
    "ShellTool",
    "ListDirTool",
    "GrepTool",
    "GlobTool",
    "WebSearchTool",
    "WebFetchTool",
    "TodosTool",
    "MemoryTool",
    "ApplyPatchTool",
]


def get_all_builtin_tools() -> list[type]:
    return [
        ReadFileTool,
        WriteFileTool,
        AppendFileTool,
        EditTool,
        ShellTool,
        ListDirTool,
        GrepTool,
        GlobTool,
        WebSearchTool,
        WebFetchTool,
        TodosTool,
        MemoryTool,
        ApplyPatchTool,
    ]
