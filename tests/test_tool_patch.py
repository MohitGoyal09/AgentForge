from __future__ import annotations

from pathlib import Path

import pytest

from agentforge_harness.tools.base import ToolInvocation
from agentforge_harness.tools.builtin.patch import ApplyPatchTool


class TestApplyPatchTool:
    async def test_applies_patch_with_intent_metadata(
        self,
        apply_patch_tool: ApplyPatchTool,
        tmp_cwd: Path,
    ):
        target = tmp_cwd / "example.txt"
        target.write_text("Hello World\n", encoding="utf-8")

        result = await apply_patch_tool.execute(
            ToolInvocation(
                cwd=tmp_cwd,
                params={
                    "intent": "Rename greeting target",
                    "patch": (
                        "--- a/example.txt\n"
                        "+++ b/example.txt\n"
                        "@@ -1 +1 @@\n"
                        "-Hello World\n"
                        "+Hello AgentForge\n"
                    ),
                },
            )
        )

        assert result.success
        assert target.read_text(encoding="utf-8") == "Hello AgentForge\n"
        assert result.metadata["intent"] == "Rename greeting target"

    async def test_creates_parent_directories_with_fallback(
        self,
        apply_patch_tool: ApplyPatchTool,
        tmp_cwd: Path,
    ):
        result = await apply_patch_tool.execute(
            ToolInvocation(
                cwd=tmp_cwd,
                params={
                    "patch": (
                        "--- /dev/null\n"
                        "+++ b/nested/example.txt\n"
                        "@@ -0,0 +1 @@\n"
                        "+created\n"
                    ),
                },
            )
        )

        assert result.success
        assert (tmp_cwd / "nested" / "example.txt").read_text(encoding="utf-8") == "created\n"

    async def test_can_require_parent_directories_to_exist(
        self,
        apply_patch_tool: ApplyPatchTool,
        tmp_cwd: Path,
    ):
        result = await apply_patch_tool.execute(
            ToolInvocation(
                cwd=tmp_cwd,
                params={
                    "create_parent_dirs": False,
                    "patch": (
                        "--- /dev/null\n"
                        "+++ b/nested/example.txt\n"
                        "@@ -0,0 +1 @@\n"
                        "+created\n"
                    ),
                },
            )
        )

        assert not result.success
        assert "Parent directory does not exist" in result.error
        assert not (tmp_cwd / "nested" / "example.txt").exists()

    async def test_deletion_patch_removes_file_with_fallback(
        self,
        apply_patch_tool: ApplyPatchTool,
        tmp_cwd: Path,
    ):
        target = tmp_cwd / "obsolete.txt"
        target.write_text("remove me\n", encoding="utf-8")

        result = await apply_patch_tool.execute(
            ToolInvocation(
                cwd=tmp_cwd,
                params={
                    "patch": (
                        "--- a/obsolete.txt\n"
                        "+++ /dev/null\n"
                        "@@ -1 +0,0 @@\n"
                        "-remove me\n"
                    ),
                },
            )
        )

        assert result.success
        assert not target.exists()

    async def test_dry_run_does_not_create_parent_directories(
        self,
        apply_patch_tool: ApplyPatchTool,
        tmp_cwd: Path,
    ):
        result = await apply_patch_tool.execute(
            ToolInvocation(
                cwd=tmp_cwd,
                params={
                    "dry_run": True,
                    "patch": (
                        "--- /dev/null\n"
                        "+++ b/nested/example.txt\n"
                        "@@ -0,0 +1 @@\n"
                        "+created\n"
                    ),
                },
            )
        )

        assert result.success
        assert not (tmp_cwd / "nested").exists()

    async def test_preserves_no_trailing_newline_marker(
        self,
        apply_patch_tool: ApplyPatchTool,
        tmp_cwd: Path,
    ):
        target = tmp_cwd / "no-newline.txt"
        target.write_text("old", encoding="utf-8")

        result = await apply_patch_tool.execute(
            ToolInvocation(
                cwd=tmp_cwd,
                params={
                    "patch": (
                        "--- a/no-newline.txt\n"
                        "+++ b/no-newline.txt\n"
                        "@@ -1 +1 @@\n"
                        "-old\n"
                        "\\ No newline at end of file\n"
                        "+new\n"
                        "\\ No newline at end of file\n"
                    ),
                },
            )
        )

        assert result.success
        assert target.read_text(encoding="utf-8") == "new"

    async def test_rejects_symlink_escape(
        self,
        apply_patch_tool: ApplyPatchTool,
        tmp_cwd: Path,
        tmp_path: Path,
    ):
        if not hasattr(Path, "symlink_to"):
            pytest.skip("symlink support unavailable")

        outside = tmp_path / "outside.txt"
        outside.write_text("outside\n", encoding="utf-8")
        link = tmp_cwd / "link.txt"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("symlink creation unavailable")

        result = await apply_patch_tool.execute(
            ToolInvocation(
                cwd=tmp_cwd,
                params={
                    "patch": (
                        "--- a/link.txt\n"
                        "+++ b/link.txt\n"
                        "@@ -1 +1 @@\n"
                        "-outside\n"
                        "+changed\n"
                    ),
                },
            )
        )

        assert not result.success
        assert "escapes workspace" in result.error
        assert outside.read_text(encoding="utf-8") == "outside\n"
