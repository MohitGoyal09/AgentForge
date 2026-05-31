from __future__ import annotations

from agentforge_harness.tools.base import ToolInvocation


class TestTodosTool:
    async def test_add_todo(self, todos_tool, invocation):
        inv = ToolInvocation(
            params={"action": "add", "content": "Fix login bug"},
            cwd=invocation.cwd,
        )
        result = await todos_tool.execute(inv)
        assert result.success
        assert "Fix login bug" in result.output
        assert result.metadata.get("todo_id")

    async def test_add_missing_content_returns_error(self, todos_tool, invocation):
        inv = ToolInvocation(params={"action": "add"}, cwd=invocation.cwd)
        result = await todos_tool.execute(inv)
        assert not result.success
        assert "content" in result.error.lower()

    async def test_list_empty(self, todos_tool, invocation):
        inv = ToolInvocation(params={"action": "list"}, cwd=invocation.cwd)
        result = await todos_tool.execute(inv)
        assert result.success
        assert "No todos" in result.output or "No active" in result.output

    async def test_list_after_add(self, todos_tool, invocation):
        await todos_tool.execute(
            ToolInvocation(params={"action": "add", "content": "Task A"}, cwd=invocation.cwd)
        )
        await todos_tool.execute(
            ToolInvocation(params={"action": "add", "content": "Task B"}, cwd=invocation.cwd)
        )
        result = await todos_tool.execute(
            ToolInvocation(params={"action": "list"}, cwd=invocation.cwd)
        )
        assert result.success
        assert "Task A" in result.output
        assert "Task B" in result.output

    async def test_complete_todo(self, todos_tool, invocation):
        add = await todos_tool.execute(
            ToolInvocation(params={"action": "add", "content": "Do something"}, cwd=invocation.cwd)
        )
        todo_id = add.metadata["todo_id"]

        result = await todos_tool.execute(
            ToolInvocation(params={"action": "complete", "id": todo_id}, cwd=invocation.cwd)
        )
        assert result.success
        assert "Completed" in result.output

        # verify list is empty
        list_result = await todos_tool.execute(
            ToolInvocation(params={"action": "list"}, cwd=invocation.cwd)
        )
        assert "No todos" in list_result.output or "No active" in list_result.output

    async def test_complete_missing_id_returns_error(self, todos_tool, invocation):
        result = await todos_tool.execute(
            ToolInvocation(params={"action": "complete"}, cwd=invocation.cwd)
        )
        assert not result.success
        assert "id" in result.error.lower()

    async def test_complete_nonexistent_id_returns_error(self, todos_tool, invocation):
        result = await todos_tool.execute(
            ToolInvocation(params={"action": "complete", "id": "badid"}, cwd=invocation.cwd)
        )
        assert not result.success
        assert "not found" in result.error.lower()

    async def test_clear_todos(self, todos_tool, invocation):
        await todos_tool.execute(
            ToolInvocation(params={"action": "add", "content": "Task"}, cwd=invocation.cwd)
        )
        result = await todos_tool.execute(
            ToolInvocation(params={"action": "clear"}, cwd=invocation.cwd)
        )
        assert result.success
        assert "Cleared" in result.output

    async def test_unknown_action_returns_error(self, todos_tool, invocation):
        result = await todos_tool.execute(
            ToolInvocation(params={"action": "unknown"}, cwd=invocation.cwd)
        )
        assert not result.success
        assert "Unknown action" in result.error

    async def test_next_actions_on_add(self, todos_tool, invocation):
        result = await todos_tool.execute(
            ToolInvocation(params={"action": "add", "content": "Task"}, cwd=invocation.cwd)
        )
        assert result.next_actions

    async def test_artifacts_on_add(self, todos_tool, invocation):
        result = await todos_tool.execute(
            ToolInvocation(params={"action": "add", "content": "Task"}, cwd=invocation.cwd)
        )
        assert len(result.artifacts) == 1
        assert result.artifacts[0] == result.metadata["todo_id"]

    async def test_recovery_hint_on_missing_content(self, todos_tool, invocation):
        result = await todos_tool.execute(
            ToolInvocation(params={"action": "add"}, cwd=invocation.cwd)
        )
        assert result.recovery_hint
