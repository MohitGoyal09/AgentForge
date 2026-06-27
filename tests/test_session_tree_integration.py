"""Integration tests for the session-history tree wired into ContextManager
and Session.  All 5 tests are purely additive — they do not modify existing
behavior, only assert new behaviour added in the session-tree integration.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agentforge_harness.agent.persistence import PersistenceManager, SessionSnapshot
from agentforge_harness.agent.session import Session
from agentforge_harness.agent.session_store import SessionTreeStore
from agentforge_harness.agent.session_tree import SessionEntry, KIND_COMPACTION, KIND_MESSAGE
from agentforge_harness.client.response import TokenUsage
from agentforge_harness.config.config import Config
from agentforge_harness.context.manager import ContextManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager(tmp_path: Path) -> ContextManager:
    config = Config(cwd=tmp_path, model_name="test/test-model")
    return ContextManager(config=config)


class _FakeCompactor:
    """Synchronous-style fake; compress() is an async method."""

    def __init__(self, summary: str = "fake summary") -> None:
        self.summary = summary

    async def compress(self, context_manager, messages=None):
        return self.summary, TokenUsage(
            prompt_tokens=1, completion_tokens=2, total_tokens=3
        )


# ---------------------------------------------------------------------------
# Test 1: add_* methods mirror into entry log with correct chain
# ---------------------------------------------------------------------------


def test_add_messages_mirrors_into_entry_log(tmp_path):
    manager = _make_manager(tmp_path)

    manager.add_user_message("hello")
    manager.add_assistant_message("hi there", [])
    manager.add_tool_result("tc1", "tool output")

    entries = manager.get_entries()
    assert len(entries) == 3, f"Expected 3 entries, got {len(entries)}"

    # All entries must be message kind
    for e in entries:
        assert e.kind == KIND_MESSAGE

    # Chain: each entry's parent_id is the previous entry's id
    assert entries[0].parent_id is None
    assert entries[1].parent_id == entries[0].id
    assert entries[2].parent_id == entries[1].id

    # Each MessageItem.entry_id is populated and matches the entry id
    messages = manager._messages
    assert len(messages) == 3
    assert messages[0].entry_id == entries[0].id
    assert messages[1].entry_id == entries[1].id
    assert messages[2].entry_id == entries[2].id


# ---------------------------------------------------------------------------
# Test 2: compaction records a non-destructive entry in the log
# ---------------------------------------------------------------------------


async def test_compaction_records_nondestructive_entry(tmp_path):
    manager = _make_manager(tmp_path)

    # Add more messages than KEEP_RECENT_TURNS (5) to trigger compaction
    for i in range(8):
        manager.add_user_message(f"user message {i}")

    # Capture the entry ids of the original messages BEFORE compaction
    original_entries = manager.get_entries()
    assert len(original_entries) == 8

    original_entry_ids = {e.id for e in original_entries}

    compactor = _FakeCompactor(summary="a great summary")
    summary, usage = await manager.compress_old_messages(compactor)

    assert summary == "a great summary"

    # (a) In-memory messages reflect the compaction (summary replaced old messages)
    in_memory = manager.get_messages()
    roles = [m["role"] for m in in_memory if m["role"] != "system"]
    # The first in-memory message should be the continuation/summary message
    contents = [m["content"] for m in in_memory if m["role"] != "system"]
    assert any("a great summary" in c for c in contents), (
        f"Expected summary in messages: {contents}"
    )

    # (b) Original message entries are still present in get_entries()
    all_entries = manager.get_entries()
    entry_ids_in_log = {e.id for e in all_entries}
    for orig_id in original_entry_ids:
        assert orig_id in entry_ids_in_log, (
            f"Original entry {orig_id} was lost from the log"
        )

    # (c) A new compaction entry was appended
    compaction_entries = [e for e in all_entries if e.kind == KIND_COMPACTION]
    assert len(compaction_entries) == 1, (
        f"Expected exactly 1 compaction entry, got {len(compaction_entries)}"
    )

    compaction_entry = compaction_entries[0]
    # The compaction entry's replaces list must include the original message ids
    # (only the old_messages — the KEEP_RECENT_TURNS remain)
    kept = 5  # KEEP_RECENT_TURNS
    old_count = 8 - kept
    for orig_entry in original_entries[:old_count]:
        assert orig_entry.id in compaction_entry.payload["replaces"], (
            f"Entry {orig_entry.id} not listed in compaction replaces"
        )


# ---------------------------------------------------------------------------
# Test 3: load_from_entries reconstructs messages in order
# ---------------------------------------------------------------------------


def test_load_from_entries_reconstructs(tmp_path):
    ts = "2024-01-01T00:00:00"
    entry_a = SessionEntry.message(
        parent_id=None,
        timestamp=ts,
        role="user",
        content="hello from entry",
        entry_id="e-a",
    )
    entry_b = SessionEntry.message(
        parent_id="e-a",
        timestamp=ts,
        role="assistant",
        content="reply from entry",
        entry_id="e-b",
    )
    entry_c = SessionEntry.message(
        parent_id="e-b",
        timestamp=ts,
        role="tool",
        content="tool result",
        tool_call_id="tc-1",
        entry_id="e-c",
    )

    manager = _make_manager(tmp_path)
    manager.load_from_entries([entry_a, entry_b, entry_c])

    msgs = manager.get_messages()
    # Strip system message
    chat_msgs = [m for m in msgs if m["role"] != "system"]

    assert len(chat_msgs) == 3
    assert chat_msgs[0]["role"] == "user"
    assert chat_msgs[0]["content"] == "hello from entry"
    assert chat_msgs[1]["role"] == "assistant"
    assert chat_msgs[1]["content"] == "reply from entry"
    assert chat_msgs[2]["role"] == "tool"
    assert chat_msgs[2]["content"] == "tool result"


# ---------------------------------------------------------------------------
# Test 4: save_session writes tree; new Session restores from it
# ---------------------------------------------------------------------------


async def test_session_save_writes_tree_and_restore_reconstructs(tmp_path):
    persistence = PersistenceManager(data_dir=tmp_path)

    session = Session(
        config=Config(cwd=tmp_path, model_name="test/test-model"),
        persistence=persistence,
    )
    await session.initialize()

    session.context_manager.add_user_message("remember this")
    session.context_manager.add_assistant_message("I will remember", [])

    session.save_session()

    # Verify tree file was created
    tree_file = tmp_path / "session_trees" / f"{session.session_id}.jsonl"
    assert tree_file.exists(), "Tree JSONL file was not created by save_session()"

    stored_entries = session.tree_store.read_all(session.session_id)
    assert len(stored_entries) == 2

    # Load the saved snapshot
    saved_snapshot = persistence.load_session(session.session_id)
    assert saved_snapshot is not None

    # Create a new Session and restore from the snapshot
    session2 = Session(
        config=Config(cwd=tmp_path, model_name="test/test-model"),
        persistence=persistence,
    )
    await session2.initialize()
    session2.restore_snapshot(saved_snapshot)

    msgs = session2.context_manager.get_messages()
    chat_msgs = [m for m in msgs if m["role"] != "system"]
    assert len(chat_msgs) == 2
    assert chat_msgs[0]["content"] == "remember this"
    assert chat_msgs[1]["content"] == "I will remember"


# ---------------------------------------------------------------------------
# Test 5: restore_snapshot falls back to flat messages when no tree file
# ---------------------------------------------------------------------------


async def test_restore_without_tree_falls_back_to_flat(tmp_path):
    persistence = PersistenceManager(data_dir=tmp_path)

    # Build a snapshot manually — no tree file will exist for this session_id
    snapshot = SessionSnapshot(
        session_id="no-tree-session",
        name="test",
        created_at=__import__("datetime").datetime(2024, 1, 1),
        updated_at=__import__("datetime").datetime(2024, 1, 1),
        turn_count=1,
        cwd=str(tmp_path),
        config={},
        messages=[
            {
                "role": "user",
                "content": "flat message",
                "tool_call_id": None,
                "tool_calls": [],
                "token_count": None,
            }
        ],
        latest_usage=TokenUsage(),
        total_usage=TokenUsage(),
        active_tools=[],
        mcp_servers=[],
        active_skills=[],
        todos={},
    )

    session = Session(
        config=Config(cwd=tmp_path, model_name="test/test-model"),
        persistence=persistence,
    )
    await session.initialize()

    # Should not crash; no tree file exists for "no-tree-session"
    session.restore_snapshot(snapshot)

    msgs = session.context_manager.get_messages()
    chat_msgs = [m for m in msgs if m["role"] != "system"]
    assert len(chat_msgs) == 1
    assert chat_msgs[0]["content"] == "flat message"
