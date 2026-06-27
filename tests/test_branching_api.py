"""Tests for P2.1 layer 4 — Branching API.

Four tests specified in docs/IMPROVEMENT-PLAN.md:
  1. branch → live messages == rewound path
  2. new messages after branching extend the new branch
  3. original branch still reconstructable from its leaf
  4. save → restore preserves the active branch
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agentforge_harness.agent.persistence import PersistenceManager
from agentforge_harness.agent.session import Session
from agentforge_harness.agent.session_tree import (
    KIND_LEAF,
    KIND_MESSAGE,
    active_leaf_id,
    path_to_entry,
    reconstruct_messages,
)
from agentforge_harness.config.config import Config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(tmp_path: Path) -> Session:
    config = Config(cwd=tmp_path, model_name="test/test-model")
    persistence = PersistenceManager(data_dir=tmp_path)
    session = Session(config=config, persistence=persistence)
    return session


async def _init(session: Session) -> None:
    await session.initialize()


def _messages_content(session: Session) -> list[str]:
    """Return ordered list of message content strings from live _messages."""
    assert session.context_manager is not None
    return [m.content for m in session.context_manager._messages]


# ---------------------------------------------------------------------------
# Test 1: branch_to_entry loads correct messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_branch_to_entry_loads_correct_messages(tmp_path):
    session = _make_session(tmp_path)
    await _init(session)
    cm = session.context_manager
    assert cm is not None

    cm.add_user_message("msg-A")
    cm.add_assistant_message("msg-B", [])
    cm.add_user_message("msg-C")
    cm.add_assistant_message("msg-D", [])

    # Capture the entry id of msg-B (second entry)
    entries_before = cm.get_entries()
    msg_b_id = entries_before[1].id  # 0=A, 1=B, 2=C, 3=D

    # Branch back to msg-B
    session.branch_to_entry(msg_b_id)

    # Live messages must now be exactly [A, B]
    live = _messages_content(session)
    assert live == ["msg-A", "msg-B"], f"Expected [A, B], got {live}"


# ---------------------------------------------------------------------------
# Test 2: new messages after branching extend the new branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_messages_extend_new_branch(tmp_path):
    session = _make_session(tmp_path)
    await _init(session)
    cm = session.context_manager
    assert cm is not None

    cm.add_user_message("msg-A")
    cm.add_assistant_message("msg-B", [])
    cm.add_user_message("msg-C")

    entries_before = cm.get_entries()
    msg_a_id = entries_before[0].id  # branch back to A

    session.branch_to_entry(msg_a_id)

    # Add a new message on the new branch
    cm.add_user_message("msg-X")

    live = _messages_content(session)
    assert live == ["msg-A", "msg-X"], f"Expected [A, X], got {live}"

    # The new entry must be parented off msg-A (not msg-C)
    new_entries = cm.get_entries()
    msg_x_entry = new_entries[-1]
    assert msg_x_entry.kind == KIND_MESSAGE
    assert msg_x_entry.payload.get("content") == "msg-X"
    assert msg_x_entry.parent_id == msg_a_id


# ---------------------------------------------------------------------------
# Test 3: original branch still reconstructable from its leaf
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_original_branch_reconstructable(tmp_path):
    session = _make_session(tmp_path)
    await _init(session)
    cm = session.context_manager
    assert cm is not None

    cm.add_user_message("msg-A")
    cm.add_assistant_message("msg-B", [])
    cm.add_user_message("msg-C")

    # Record the last entry id before branching — that is the original tip
    entries_before = cm.get_entries()
    original_tip_id = entries_before[-1].id  # msg-C
    msg_a_id = entries_before[0].id

    session.branch_to_entry(msg_a_id)

    # After branching the store was written; read entries from disk
    store_entries = session.tree_store.read_all(session.session_id)

    # Original branch: reconstruct from original_tip_id
    original_msgs = reconstruct_messages(store_entries, leaf_id=original_tip_id)
    contents = [m["content"] for m in original_msgs]
    assert contents == ["msg-A", "msg-B", "msg-C"], (
        f"Original branch not reconstructable: {contents}"
    )


# ---------------------------------------------------------------------------
# Test 4: save → restore preserves the active branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_restore_preserves_active_branch(tmp_path):
    session = _make_session(tmp_path)
    await _init(session)
    cm = session.context_manager
    assert cm is not None

    cm.add_user_message("msg-A")
    cm.add_assistant_message("msg-B", [])
    cm.add_user_message("msg-C")

    entries_before = cm.get_entries()
    msg_a_id = entries_before[0].id

    session.branch_to_entry(msg_a_id)

    # Add a message on the new branch
    cm.add_user_message("msg-X")

    live_before = _messages_content(session)

    # Save
    session.save_session()
    saved_id = session.session_id

    # Restore into a fresh session
    session2 = _make_session(tmp_path)
    await _init(session2)
    snapshot = session2.persistence.load_session(saved_id)
    assert snapshot is not None
    session2.restore_snapshot(snapshot)

    live_after = _messages_content(session2)
    assert live_after == live_before, (
        f"Restore changed live messages.\nBefore: {live_before}\nAfter:  {live_after}"
    )


# ---------------------------------------------------------------------------
# Test 5: tree_choices returns only KIND_MESSAGE entries on active path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tree_choices_returns_message_entries(tmp_path):
    session = _make_session(tmp_path)
    await _init(session)
    cm = session.context_manager
    assert cm is not None

    cm.add_user_message("hello")
    cm.add_assistant_message("world", [])
    cm.add_user_message("foo")

    choices = session.tree_choices()
    assert len(choices) == 3
    assert all(c["role"] in ("user", "assistant") for c in choices)
    assert choices[0]["preview"] == "hello"
    assert choices[1]["preview"] == "world"
    assert choices[2]["preview"] == "foo"
    assert [c["position"] for c in choices] == [0, 1, 2]


# ---------------------------------------------------------------------------
# Test 6: branch_to_entry raises on bad entry_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_branch_to_entry_raises_on_unknown_id(tmp_path):
    session = _make_session(tmp_path)
    await _init(session)
    cm = session.context_manager
    assert cm is not None
    cm.add_user_message("hello")

    with pytest.raises(ValueError, match="Unknown entry_id"):
        session.branch_to_entry("nonexistent_id_xyz")
