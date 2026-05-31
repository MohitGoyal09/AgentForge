from __future__ import annotations

from pathlib import Path

from agentforge_harness.tools.base import ToolInvocation


class TestShellTool:
    async def test_blocked_commands(self, shell_tool):
        blocked = [
            "rm -rf /",
            "rm -rf /*",
            "mkfs.ext4 /dev/sda1",
            "chmod 777 /etc",
            "shutdown -h now",
        ]
        for cmd in blocked:
            inv = ToolInvocation(params={"command": cmd}, cwd=Path("/tmp"))
            result = await shell_tool.execute(inv)
            assert not result.success, f"Command should be blocked: {cmd}"
            assert "blocked" in result.error.lower() or "Blocked" in result.error

    async def test_blocked_recovery_hint(self, shell_tool):
        inv = ToolInvocation(params={"command": "rm -rf /"}, cwd=Path("/tmp"))
        result = await shell_tool.execute(inv)
        assert result.recovery_hint

    async def test_blocked_metadata(self, shell_tool):
        inv = ToolInvocation(params={"command": "rm -rf /"}, cwd=Path("/tmp"))
        result = await shell_tool.execute(inv)
        assert result.metadata.get("blocked") is True

    async def test_nonexistent_cwd_returns_error(self, shell_tool):
        inv = ToolInvocation(
            params={"command": "echo hi", "cwd": "/nonexistent/path"},
            cwd=Path("/tmp"),
        )
        result = await shell_tool.execute(inv)
        assert not result.success
        assert "not found" in result.summary.lower() if result.summary else True

    async def test_successful_command(self, shell_tool, tmp_cwd):
        inv = ToolInvocation(params={"command": "echo hello world"}, cwd=tmp_cwd)
        result = await shell_tool.execute(inv)
        assert result.success
        assert "hello world" in result.output

    async def test_failing_command(self, shell_tool, tmp_cwd):
        inv = ToolInvocation(params={"command": "false"}, cwd=tmp_cwd)
        result = await shell_tool.execute(inv)
        assert not result.success

    async def test_exit_code_on_success(self, shell_tool, tmp_cwd):
        inv = ToolInvocation(params={"command": "echo ok"}, cwd=tmp_cwd)
        result = await shell_tool.execute(inv)
        assert result.exit_code == 0

    async def test_exit_code_on_failure(self, shell_tool, tmp_cwd):
        inv = ToolInvocation(params={"command": "false"}, cwd=tmp_cwd)
        result = await shell_tool.execute(inv)
        assert result.exit_code != 0

    async def test_next_actions_on_success(self, shell_tool, tmp_cwd):
        inv = ToolInvocation(params={"command": "echo test"}, cwd=tmp_cwd)
        result = await shell_tool.execute(inv)
        assert result.next_actions

    async def test_artifacts_on_success(self, shell_tool, tmp_cwd):
        inv = ToolInvocation(params={"command": "echo test"}, cwd=tmp_cwd)
        result = await shell_tool.execute(inv)
        assert len(result.artifacts) == 1

    async def test_summary_on_success(self, shell_tool, tmp_cwd):
        inv = ToolInvocation(params={"command": "echo test"}, cwd=tmp_cwd)
        result = await shell_tool.execute(inv)
        assert result.summary
        assert "exit 0" in result.summary

    async def test_summary_on_failure(self, shell_tool, tmp_cwd):
        inv = ToolInvocation(params={"command": "false"}, cwd=tmp_cwd)
        result = await shell_tool.execute(inv)
        assert result.summary
        assert "failed" in result.summary.lower()

    async def test_stderr_is_captured(self, shell_tool, tmp_cwd):
        inv = ToolInvocation(params={"command": "echo stderr >&2"}, cwd=tmp_cwd)
        result = await shell_tool.execute(inv)
        assert result.success
        assert "stderr" in result.output

    async def test_output_truncated(self, shell_tool, tmp_cwd):
        """Output over 100KB should be truncated."""
        inv = ToolInvocation(params={"command": "python3 -c \"print('x' * 200000)\""}, cwd=tmp_cwd)
        result = await shell_tool.execute(inv)
        assert result.success
        assert "... [output truncated]" in result.output
