from __future__ import annotations

from pathlib import Path
import pytest

from config.config import Config
from tools.base import ToolInvocation
from tools.builtin.todo import TodosTool
from tools.builtin.memory import MemoryTool
from tools.builtin.shell import ShellTool
from tools.builtin.read_file import ReadFileTool
from tools.builtin.write_file import WriteFileTool
from tools.builtin.append_file import AppendFileTool
from tools.builtin.edit_file import EditTool
from tools.builtin.list_dir import ListDirTool
from tools.builtin.grep import GrepTool
from tools.builtin.glob import GlobTool
from tools.builtin.web_search import WebSearchTool
from tools.builtin.web_fetch import WebFetchTool


@pytest.fixture
def config() -> Config:
    return Config(
        cwd=Path("/tmp"),
        model_name="test/test-model",
    )


@pytest.fixture
def alt_config(tmp_path: Path) -> Config:
    return Config(
        cwd=tmp_path,
        model_name="test/test-model",
    )


@pytest.fixture
def tmp_cwd(tmp_path: Path) -> Path:
    cwd = tmp_path / "workspace"
    cwd.mkdir()
    return cwd


@pytest.fixture
def invocation(tmp_cwd: Path) -> ToolInvocation:
    return ToolInvocation(params={}, cwd=tmp_cwd)


@pytest.fixture
def todos_tool(config: Config) -> TodosTool:
    return TodosTool(config)


@pytest.fixture
def memory_tool(alt_config: Config, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MemoryTool:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr("tools.builtin.memory.get_data_dir", lambda: data_dir)
    return MemoryTool(alt_config)


@pytest.fixture
def shell_tool(config: Config) -> ShellTool:
    return ShellTool(config)


@pytest.fixture
def read_file_tool(config: Config) -> ReadFileTool:
    return ReadFileTool(config)


@pytest.fixture
def write_file_tool(config: Config) -> WriteFileTool:
    return WriteFileTool(config)


@pytest.fixture
def append_file_tool(config: Config) -> AppendFileTool:
    return AppendFileTool(config)


@pytest.fixture
def edit_file_tool(config: Config) -> EditTool:
    return EditTool(config)


@pytest.fixture
def list_dir_tool(config: Config) -> ListDirTool:
    return ListDirTool(config)


@pytest.fixture
def grep_tool(config: Config) -> GrepTool:
    return GrepTool(config)


@pytest.fixture
def glob_tool(config: Config) -> GlobTool:
    return GlobTool(config)


@pytest.fixture
def web_search_tool(config: Config) -> WebSearchTool:
    return WebSearchTool(config)


@pytest.fixture
def web_fetch_tool(config: Config) -> WebFetchTool:
    return WebFetchTool(config)
