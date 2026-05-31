from __future__ import annotations

from agentforge_harness.tools.base import ToolInvocation


class TestMemoryTool:
    async def test_set_and_get(self, memory_tool, invocation):
        set_result = await memory_tool.execute(
            ToolInvocation(params={"action": "set", "key": "color", "value": "blue"}, cwd=invocation.cwd)
        )
        assert set_result.success
        assert "color" in set_result.output

        get_result = await memory_tool.execute(
            ToolInvocation(params={"action": "get", "key": "color"}, cwd=invocation.cwd)
        )
        assert get_result.success
        assert "blue" in get_result.output

    async def test_get_nonexistent_key(self, memory_tool, invocation):
        result = await memory_tool.execute(
            ToolInvocation(params={"action": "get", "key": "nonexistent"}, cwd=invocation.cwd)
        )
        assert result.success
        assert "not found" in result.output.lower()

    async def test_set_missing_key_returns_error(self, memory_tool, invocation):
        result = await memory_tool.execute(
            ToolInvocation(params={"action": "set", "value": "x"}, cwd=invocation.cwd)
        )
        assert not result.success
        assert "key" in result.error.lower()

    async def test_set_missing_value_returns_error(self, memory_tool, invocation):
        result = await memory_tool.execute(
            ToolInvocation(params={"action": "set", "key": "x"}, cwd=invocation.cwd)
        )
        assert not result.success
        assert "value" in result.error.lower()

    async def test_get_missing_key_param_returns_error(self, memory_tool, invocation):
        result = await memory_tool.execute(
            ToolInvocation(params={"action": "get"}, cwd=invocation.cwd)
        )
        assert not result.success

    async def test_delete_existing(self, memory_tool, invocation):
        await memory_tool.execute(
            ToolInvocation(params={"action": "set", "key": "foo", "value": "bar"}, cwd=invocation.cwd)
        )
        result = await memory_tool.execute(
            ToolInvocation(params={"action": "delete", "key": "foo"}, cwd=invocation.cwd)
        )
        assert result.success
        assert "Deleted" in result.output

    async def test_delete_missing_key_param_returns_error(self, memory_tool, invocation):
        result = await memory_tool.execute(
            ToolInvocation(params={"action": "delete"}, cwd=invocation.cwd)
        )
        assert not result.success

    async def test_delete_nonexistent_key(self, memory_tool, invocation):
        result = await memory_tool.execute(
            ToolInvocation(params={"action": "delete", "key": "nonexistent"}, cwd=invocation.cwd)
        )
        assert result.success

    async def test_list_after_set(self, memory_tool, invocation):
        await memory_tool.execute(
            ToolInvocation(params={"action": "set", "key": "a", "value": "1"}, cwd=invocation.cwd)
        )
        await memory_tool.execute(
            ToolInvocation(params={"action": "set", "key": "b", "value": "2"}, cwd=invocation.cwd)
        )
        result = await memory_tool.execute(
            ToolInvocation(params={"action": "list"}, cwd=invocation.cwd)
        )
        assert result.success
        assert "a: 1" in result.output
        assert "b: 2" in result.output

    async def test_list_empty(self, memory_tool, invocation):
        result = await memory_tool.execute(
            ToolInvocation(params={"action": "list"}, cwd=invocation.cwd)
        )
        assert result.success
        assert "No" in result.output

    async def test_clear(self, memory_tool, invocation):
        await memory_tool.execute(
            ToolInvocation(params={"action": "set", "key": "x", "value": "y"}, cwd=invocation.cwd)
        )
        result = await memory_tool.execute(
            ToolInvocation(params={"action": "clear"}, cwd=invocation.cwd)
        )
        assert result.success
        assert "Cleared" in result.output

        list_result = await memory_tool.execute(
            ToolInvocation(params={"action": "list"}, cwd=invocation.cwd)
        )
        assert "No" in list_result.output

    async def test_unknown_action_returns_error(self, memory_tool, invocation):
        result = await memory_tool.execute(
            ToolInvocation(params={"action": "unknown"}, cwd=invocation.cwd)
        )
        assert not result.success
        assert "Unknown action" in result.error

    async def test_next_actions_on_set(self, memory_tool, invocation):
        result = await memory_tool.execute(
            ToolInvocation(params={"action": "set", "key": "x", "value": "y"}, cwd=invocation.cwd)
        )
        assert result.next_actions

    async def test_artifacts_on_set(self, memory_tool, invocation):
        result = await memory_tool.execute(
            ToolInvocation(params={"action": "set", "key": "x", "value": "y"}, cwd=invocation.cwd)
        )
        assert len(result.artifacts) == 1
        assert result.artifacts[0] == "x"

    async def test_recovery_hint_on_missing_key(self, memory_tool, invocation):
        result = await memory_tool.execute(
            ToolInvocation(params={"action": "set", "value": "x"}, cwd=invocation.cwd)
        )
        assert result.recovery_hint

    async def test_recovery_hint_on_unknown_action(self, memory_tool, invocation):
        result = await memory_tool.execute(
            ToolInvocation(params={"action": "bad"}, cwd=invocation.cwd)
        )
        assert result.recovery_hint

    async def test_list_gives_next_actions(self, memory_tool, invocation):
        await memory_tool.execute(
            ToolInvocation(params={"action": "set", "key": "a", "value": "b"}, cwd=invocation.cwd)
        )
        result = await memory_tool.execute(
            ToolInvocation(params={"action": "list"}, cwd=invocation.cwd)
        )
        assert result.next_actions

    async def test_get_from_empty_returns_not_found(self, memory_tool, invocation):
        result = await memory_tool.execute(
            ToolInvocation(params={"action": "get", "key": "anything"}, cwd=invocation.cwd)
        )
        assert result.success
        assert "not found" in result.output.lower()
