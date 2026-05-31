from __future__ import annotations

import subprocess
from pathlib import Path

from agentforge_harness.tools.base import ToolInvocation
from agentforge_harness.tools.builtin.git_diff import GitDiffTool


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _init_repo(path: Path) -> None:
    _git(path, "init")
    _git(path, "config", "user.email", "agentforge@example.com")
    _git(path, "config", "user.name", "AgentForge Tests")
    (path / "tracked.txt").write_text("hello\n", encoding="utf-8")
    _git(path, "add", "tracked.txt")
    _git(path, "commit", "-m", "initial")


class TestGitDiffTool:
    async def test_returns_working_tree_diff(self, git_diff_tool: GitDiffTool, tmp_cwd: Path):
        _init_repo(tmp_cwd)
        (tmp_cwd / "tracked.txt").write_text("hello\nworld\n", encoding="utf-8")

        result = await git_diff_tool.execute(ToolInvocation(params={}, cwd=tmp_cwd))

        assert result.success
        assert "Diff:" in result.output
        assert "+world" in result.output
        assert result.metadata["changed_files"] == ["tracked.txt"]
        assert result.diff_text is not None

    async def test_limits_diff_to_path(self, git_diff_tool: GitDiffTool, tmp_cwd: Path):
        _init_repo(tmp_cwd)
        (tmp_cwd / "tracked.txt").write_text("changed\n", encoding="utf-8")
        (tmp_cwd / "other.txt").write_text("other\n", encoding="utf-8")

        result = await git_diff_tool.execute(
            ToolInvocation(params={"path": "tracked.txt"}, cwd=tmp_cwd)
        )

        assert result.success
        assert "tracked.txt" in result.output
        assert "other.txt" not in result.output

    async def test_rejects_path_outside_repo(self, git_diff_tool: GitDiffTool, tmp_cwd: Path, tmp_path: Path):
        _init_repo(tmp_cwd)
        outside = tmp_path / "outside.txt"
        outside.write_text("outside", encoding="utf-8")

        result = await git_diff_tool.execute(
            ToolInvocation(params={"path": str(outside)}, cwd=tmp_cwd)
        )

        assert not result.success
        assert "outside repository" in result.error
        assert result.recovery_hint

    async def test_reports_non_git_directory(self, git_diff_tool: GitDiffTool, tmp_cwd: Path):
        result = await git_diff_tool.execute(ToolInvocation(params={}, cwd=tmp_cwd))

        assert not result.success
        assert "Not a git repository" in result.error
