from __future__ import annotations

from pathlib import Path

from agentforge_harness.config.config import Config
from agentforge_harness.context.manager import ContextManager


def _manager() -> ContextManager:
    return ContextManager(config=Config(cwd=Path("/tmp"), model_name="test/test-model"))


def _tool_calls(*ids: str) -> list[dict]:
    return [
        {"id": i, "type": "function", "function": {"name": "read_file", "arguments": "{}"}}
        for i in ids
    ]


def _roles_and_ids(manager: ContextManager) -> list[tuple[str, str | None]]:
    return [(m.role, m.tool_call_id) for m in manager._messages]


def test_no_repair_when_transcript_is_well_formed():
    manager = _manager()
    manager.add_user_message("hi")
    manager.add_assistant_message("calling", _tool_calls("c1"))
    manager.add_tool_result("c1", "result")

    assert manager.repair_dangling_tool_calls() == 0
    assert _roles_and_ids(manager) == [("user", None), ("assistant", None), ("tool", "c1")]


def test_repairs_dangling_tool_call_at_end_of_transcript():
    manager = _manager()
    manager.add_user_message("hi")
    manager.add_assistant_message("calling", _tool_calls("c1", "c2"))
    # interrupted: no tool results recorded

    assert manager.repair_dangling_tool_calls() == 2
    roles = _roles_and_ids(manager)
    assert roles == [
        ("user", None),
        ("assistant", None),
        ("tool", "c1"),
        ("tool", "c2"),
    ]


def test_repairs_only_missing_results():
    manager = _manager()
    manager.add_assistant_message("calling", _tool_calls("c1", "c2"))
    manager.add_tool_result("c1", "got one")
    # c2 result missing

    assert manager.repair_dangling_tool_calls() == 1
    roles = _roles_and_ids(manager)
    assert roles == [("assistant", None), ("tool", "c1"), ("tool", "c2")]


def test_inserts_results_before_a_following_user_message_on_resume():
    """Resume case: a new user message was appended after the dangling
    assistant message. Synthetic results must slot in between, not at the end."""
    manager = _manager()
    manager.add_assistant_message("calling", _tool_calls("c1"))
    manager.add_user_message("continue please")  # appended on resume

    assert manager.repair_dangling_tool_calls() == 1
    roles = _roles_and_ids(manager)
    assert roles == [
        ("assistant", None),
        ("tool", "c1"),
        ("user", None),
    ]
    # the synthetic result carries the interrupted marker
    synthetic = manager._messages[1]
    assert synthetic.content == ContextManager._INTERRUPTED_TOOL_RESULT


def test_repair_is_idempotent():
    manager = _manager()
    manager.add_assistant_message("calling", _tool_calls("c1"))

    assert manager.repair_dangling_tool_calls() == 1
    assert manager.repair_dangling_tool_calls() == 0
