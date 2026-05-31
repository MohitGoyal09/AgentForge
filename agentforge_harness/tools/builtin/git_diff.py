from __future__ import annotations

import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from agentforge_harness.tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from agentforge_harness.utils.paths import resolve_path


class GitDiffParams(BaseModel):
    path: str | None = Field(
        None,
        description="Optional file or directory path to limit the diff to.",
    )
    staged: bool = Field(
        False,
        description="Show staged changes instead of unstaged working tree changes.",
    )
    include_untracked: bool = Field(
        True,
        description="Include untracked file names in the summary when no path is specified.",
    )
    max_bytes: int = Field(
        60000,
        ge=1000,
        le=500000,
        description="Maximum diff output bytes returned to the model.",
    )


class GitDiffTool(Tool):
    name = "git_diff"
    description = (
        "Show a read-only git diff for the current repository. "
        "Use this instead of shell for inspecting code changes because it returns "
        "bounded, structured output and never mutates the repository."
    )
    kind = ToolKind.READ
    schema = GitDiffParams

    def _run_git(self, cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )

    def _repo_root(self, cwd: Path) -> Path | None:
        result = self._run_git(cwd, ["rev-parse", "--show-toplevel"])
        if result.returncode != 0:
            return None
        return Path(result.stdout.strip()).resolve()

    def _pathspec(self, cwd: Path, repo_root: Path, path: str | None) -> list[str]:
        if not path:
            return []

        target = resolve_path(cwd, path)
        try:
            target.relative_to(repo_root)
        except ValueError as e:
            raise ValueError(f"Path is outside repository: {path}") from e

        return [str(target.relative_to(repo_root))]

    def _filter_status_lines(self, status_lines: list[str], pathspec: list[str]) -> list[str]:
        if not pathspec:
            return status_lines

        def matches(line: str) -> bool:
            if len(line) < 4:
                return False
            changed_path = line[3:].strip()
            return any(
                changed_path == path or changed_path.startswith(f"{path}/")
                for path in pathspec
            )

        return [line for line in status_lines if matches(line)]

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = GitDiffParams(**invocation.params)
        cwd = invocation.cwd.resolve()
        repo_root = self._repo_root(cwd)

        if repo_root is None:
            return ToolResult.error_result(
                f"Not a git repository: {cwd}",
                summary="No git repository found",
                recovery_hint="Run git_diff from inside a git repository, or initialize one before retrying.",
            )

        try:
            pathspec = self._pathspec(cwd, repo_root, params.path)
        except ValueError as e:
            return ToolResult.error_result(
                str(e),
                summary="Invalid git diff path",
                recovery_hint="Use a path inside the current git repository, or omit path to diff all changes.",
            )

        diff_args = [
            "diff",
            "--no-ext-diff",
            "--src-prefix=a/",
            "--dst-prefix=b/",
        ]
        if params.staged:
            diff_args.append("--staged")
        if pathspec:
            diff_args.extend(["--", *pathspec])

        diff_result = self._run_git(repo_root, diff_args)
        if diff_result.returncode not in (0, 1):
            return ToolResult.error_result(
                diff_result.stderr.strip() or "git diff failed",
                output=diff_result.stdout.strip(),
                summary="git diff failed",
                recovery_hint="Check the path and repository state, then retry git_diff.",
                exit_code=diff_result.returncode,
            )

        status_result = self._run_git(repo_root, ["status", "--short", "--untracked-files=normal"])
        status_lines = status_result.stdout.splitlines() if status_result.returncode == 0 else []
        status_lines = self._filter_status_lines(status_lines, pathspec)

        untracked_lines: list[str] = []
        if params.include_untracked and not params.staged and not pathspec:
            untracked_lines = [line for line in status_lines if line.startswith("?? ")]

        sections: list[str] = []
        if status_lines:
            sections.append("Status:\n" + "\n".join(status_lines))
        if untracked_lines:
            sections.append(
                "Untracked files are listed in status but are not expanded into diff hunks."
            )

        diff_text = diff_result.stdout
        truncated = False
        encoded = diff_text.encode("utf-8")
        if len(encoded) > params.max_bytes:
            diff_text = encoded[: params.max_bytes].decode("utf-8", errors="replace")
            diff_text += "\n... [diff truncated]"
            truncated = True

        if diff_text.strip():
            sections.append("Diff:\n" + diff_text.rstrip())
        elif not sections:
            sections.append("No changes found.")

        changed_files = [
            line[3:].strip()
            for line in status_lines
            if len(line) >= 4 and (not pathspec or line[3:].strip() in pathspec)
        ]

        scope = pathspec[0] if pathspec else "repository"
        mode = "staged" if params.staged else "working tree"
        return ToolResult.success_result(
            "\n\n".join(sections),
            summary=f"Generated {mode} git diff for {scope}",
            artifacts=[str(repo_root / path) for path in changed_files],
            next_actions=[
                "Use read_file to inspect specific changed files before editing.",
                "Use apply_patch or edit_file for precise changes.",
            ],
            metadata={
                "repo_root": str(repo_root),
                "staged": params.staged,
                "path": params.path,
                "changed_files": changed_files,
                "untracked_count": len(untracked_lines),
            },
            diff_text=diff_text if diff_text else None,
            truncated=truncated,
            exit_code=diff_result.returncode,
        )
