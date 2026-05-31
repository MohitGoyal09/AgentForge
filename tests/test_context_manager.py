from __future__ import annotations

from pathlib import Path

from agentforge_harness.client.response import TokenUsage
from agentforge_harness.config.config import Config
from agentforge_harness.context.manager import ContextManager


class FakeCompactor:
    def __init__(self):
        self.messages = None

    async def compress(self, context_manager, messages=None):
        self.messages = messages
        return "summary", TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2)


async def test_compress_old_messages_preserves_message_roles():
    manager = ContextManager(config=Config(cwd=Path("/tmp"), model_name="test/test-model"))
    manager.add_user_message("first user")
    manager.add_assistant_message("assistant reply", [])
    manager.add_tool_result("tool_1", "tool output")
    manager.add_user_message("second user")
    manager.add_assistant_message("second assistant", [])
    manager.add_user_message("third user")

    compactor = FakeCompactor()
    summary, usage = await manager.compress_old_messages(compactor)

    assert summary == "summary"
    assert usage is not None
    assert compactor.messages is not None
    roles = [message["role"] for message in compactor.messages]
    assert roles == ["user"]


async def test_compress_old_messages_keeps_original_roles_when_enough_old_messages():
    manager = ContextManager(config=Config(cwd=Path("/tmp"), model_name="test/test-model"))
    manager.add_user_message("u1")
    manager.add_assistant_message("a1", [])
    manager.add_tool_result("tool_1", "tool output")
    manager.add_user_message("u2")
    manager.add_assistant_message("a2", [])
    manager.add_tool_result("tool_2", "more output")
    manager.add_user_message("u3")
    manager.add_assistant_message("a3", [])

    compactor = FakeCompactor()
    await manager.compress_old_messages(compactor)

    assert compactor.messages is not None
    roles = [message["role"] for message in compactor.messages]
    assert roles == ["user", "assistant", "tool"]
