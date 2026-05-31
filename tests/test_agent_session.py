from __future__ import annotations

from pathlib import Path

from agentforge_harness.config.config import Config
from agentforge_harness.agent.session import Session
from agentforge_harness.agent.modes import AgentMode
from agentforge_harness.client.response import TokenUsage
from agentforge_harness.agent.persistence import SessionSnapshot
from agentforge_harness.tools.base import ToolKind


class TestSessionBasics:
    def test_session_creates_with_default_mode(self):
        config = Config(cwd=Path("/tmp"), model_name="test/test-model")
        session = Session(config)
        assert session.mode == AgentMode.BUILD
        assert session._turn_count == 0

    def test_session_increments_turn(self):
        config = Config(cwd=Path("/tmp"), model_name="test/test-model")
        session = Session(config)
        assert session._turn_count == 0
        session.increment_turn()
        assert session._turn_count == 1
        session.increment_turn()
        assert session._turn_count == 2

    def test_session_id_is_unique(self):
        config = Config(cwd=Path("/tmp"), model_name="test/test-model")
        s1 = Session(config)
        s2 = Session(config)
        assert s1.session_id != s2.session_id

    def test_set_mode(self):
        config = Config(cwd=Path("/tmp"), model_name="test/test-model")
        session = Session(config)
        assert session.mode == AgentMode.BUILD
        session.set_mode(AgentMode.PLAN)
        assert session.mode == AgentMode.PLAN
        session.set_mode(AgentMode.BUILD)
        assert session.mode == AgentMode.BUILD

    def test_tool_registry_has_builtin_tools(self):
        config = Config(cwd=Path("/tmp"), model_name="test/test-model")
        session = Session(config)
        tools = session.tool_registry.get_tools()
        tool_names = [t.name for t in tools]
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "shell" in tool_names
        assert "grep" in tool_names
        assert "glob" in tool_names
        assert "list_dir" in tool_names
        assert "todos" in tool_names
        assert "memory" in tool_names
        assert "web_search" in tool_names
        assert "web_fetch" in tool_names

    def test_plan_mode_filters_write_tools(self):
        config = Config(cwd=Path("/tmp"), model_name="test/test-model")
        session = Session(config)

        plan_tools = session.tool_registry.get_tools(mode=AgentMode.PLAN)
        build_tools = session.tool_registry.get_tools(mode=AgentMode.BUILD)

        plan_names = {t.name for t in plan_tools}
        build_names = {t.name for t in build_tools}

        assert "read_file" in plan_names
        assert "write_file" not in plan_names
        assert "shell" not in plan_names

        # BUILD mode should have more tools than PLAN
        assert len(build_tools) > len(plan_tools)

    def test_plan_mode_contains_only_read_and_network(self):
        config = Config(cwd=Path("/tmp"), model_name="test/test-model")
        session = Session(config)
        plan_tools = session.tool_registry.get_tools(mode=AgentMode.PLAN)

        for tool in plan_tools:
            assert tool.kind in (ToolKind.READ, ToolKind.NETWORK), (
                f"Tool {tool.name} has kind {tool.kind} which is not allowed in PLAN mode"
            )

    def test_session_has_default_subagent_tools(self):
        config = Config(cwd=Path("/tmp"), model_name="test/test-model")
        session = Session(config)
        tools = session.tool_registry.get_tools()
        tool_names = [t.name for t in tools]
        assert "subagent_explore" in tool_names
        assert "subagent_debugger" in tool_names
        assert "subagent_code_reviewer" in tool_names

    def test_restore_snapshot_restores_mode(self):
        config = Config(cwd=Path("/tmp"), model_name="test/test-model")
        session = Session(config)
        from agentforge_harness.context.manager import ContextManager

        session.context_manager = ContextManager(
            config=config,
            tools=session.tool_registry.get_tools(mode=session.mode),
            skills=[],
            mode=session.mode,
        )
        snapshot = SessionSnapshot(
            session_id="session_plan",
            name="plan session",
            created_at=session.created_at,
            updated_at=session.updated_at,
            turn_count=2,
            cwd="/tmp",
            config={},
            messages=[],
            latest_usage=TokenUsage(),
            total_usage=TokenUsage(),
            active_tools=[],
            mcp_servers=[],
            active_skills=[],
            todos={},
            mode="plan",
        )

        session.restore_snapshot(snapshot)

        assert session.mode == AgentMode.PLAN
        plan_tools = {tool.name for tool in session.tool_registry.get_tools(mode=session.mode)}
        assert "write_file" not in plan_tools

    def test_create_snapshot_defaults_to_current_mode(self):
        config = Config(cwd=Path("/tmp"), model_name="test/test-model")
        session = Session(config)
        from agentforge_harness.context.manager import ContextManager

        session.context_manager = ContextManager(
            config=config,
            tools=session.tool_registry.get_tools(mode=AgentMode.PLAN),
            skills=[],
            mode=AgentMode.PLAN,
        )
        session.mode = AgentMode.PLAN

        snapshot = session.create_snapshot()

        assert snapshot.mode == "plan"
