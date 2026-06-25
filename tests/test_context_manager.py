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


def _budget_at_pct(pct: float) -> dict:
    window = 1000
    manager = ContextManager(
        config=Config(cwd=Path("/tmp"), model_name="test/test-model")
    )
    manager.config.model.context_window = window
    # Override the token estimate to hit a precise percentage.
    manager._estimate_current_tokens = lambda: int(window * pct / 100)  # type: ignore[method-assign]
    return manager.get_context_budget()


def test_budget_tiers_warning_compact_critical():
    assert _budget_at_pct(50)["warning"] is False
    assert _budget_at_pct(50)["should_compact"] is False
    assert _budget_at_pct(50)["critical"] is False

    assert _budget_at_pct(72)["warning"] is True
    assert _budget_at_pct(72)["should_compact"] is False

    # Regression: should_compact must fire at 80% (the old `critical` only
    # fired above 100%, so it never drove compaction).
    assert _budget_at_pct(82)["warning"] is True
    assert _budget_at_pct(82)["should_compact"] is True
    assert _budget_at_pct(82)["critical"] is False

    assert _budget_at_pct(97)["should_compact"] is True
    assert _budget_at_pct(97)["critical"] is True


def test_needs_compression_uses_compact_threshold():
    assert _budget_at_pct(85)
    manager = ContextManager(
        config=Config(cwd=Path("/tmp"), model_name="test/test-model")
    )
    manager.config.model.context_window = 1000
    manager._estimate_current_tokens = lambda: 850  # type: ignore[method-assign]
    assert manager.needs_compression() is True

    manager._estimate_current_tokens = lambda: 700  # type: ignore[method-assign]
    assert manager.needs_compression() is False


async def test_compaction_failure_is_logged_not_silent(caplog):
    import logging as _logging

    from agentforge_harness.context.compaction import ChatCompactor

    class ExplodingClient:
        async def chat_completion(self, *args, **kwargs):
            raise RuntimeError("provider down")
            yield  # pragma: no cover - makes this an async generator

    manager = ContextManager(config=Config(cwd=Path("/tmp"), model_name="test/test-model"))
    manager.add_user_message("u1")
    manager.add_assistant_message("a1", [])
    manager.add_user_message("u2")

    compactor = ChatCompactor(ExplodingClient())

    with caplog.at_level(_logging.ERROR):
        summary, usage = await compactor.compress(manager, messages=manager.get_messages())

    assert summary is None and usage is None
    assert any("compaction failed" in r.message.lower() for r in caplog.records)


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
