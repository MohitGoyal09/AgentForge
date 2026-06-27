from __future__ import annotations

import os
import platform
import sys

import pytest

from agentforge_harness.agent.session_tree import (
    SessionEntry,
    reconstruct_messages,
)
from agentforge_harness.agent.session_store import (
    SessionTreeStore,
    migrate_snapshot_to_entries,
)
from agentforge_harness.agent.persistence import SessionSnapshot
from agentforge_harness.client.response import TokenUsage
from datetime import datetime

TS = "2024-06-01T12:00:00"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(tmp_path):
    return SessionTreeStore(data_dir=tmp_path)


def _entry_a(parent_id=None):
    return SessionEntry.message(
        parent_id=parent_id,
        timestamp=TS,
        role="user",
        content="hello",
        entry_id="entry_a",
    )


def _entry_b():
    return SessionEntry.message(
        parent_id="entry_a",
        timestamp=TS,
        role="assistant",
        content="world",
        entry_id="entry_b",
    )


# ---------------------------------------------------------------------------
# test_append_and_read_roundtrip
# ---------------------------------------------------------------------------


def test_append_and_read_roundtrip(tmp_path):
    store = _make_store(tmp_path)
    sid = "session-001"

    ea = _entry_a()
    eb = _entry_b()

    store.append(sid, ea)
    store.append(sid, eb)

    result = store.read_all(sid)

    assert len(result) == 2
    assert result[0].to_dict() == ea.to_dict()
    assert result[1].to_dict() == eb.to_dict()


# ---------------------------------------------------------------------------
# test_read_missing_returns_empty
# ---------------------------------------------------------------------------


def test_read_missing_returns_empty(tmp_path):
    store = _make_store(tmp_path)
    result = store.read_all("nonexistent-session")
    assert result == []


# ---------------------------------------------------------------------------
# test_read_skips_malformed_lines
# ---------------------------------------------------------------------------


def test_read_skips_malformed_lines(tmp_path):
    store = _make_store(tmp_path)
    sid = "session-skip"

    # Build a valid entry to serialise
    ea = _entry_a()
    good_line = __import__("json").dumps(ea.to_dict()) + "\n"
    bad_line = "{garbage not json\n"

    file_path = store._path(sid)
    with open(file_path, "w", encoding="utf-8") as fp:
        fp.write(good_line)
        fp.write(bad_line)

    result = store.read_all(sid)

    assert len(result) == 1
    assert result[0].to_dict() == ea.to_dict()


# ---------------------------------------------------------------------------
# test_invalid_session_id_rejected
# ---------------------------------------------------------------------------


def test_invalid_session_id_rejected(tmp_path):
    store = _make_store(tmp_path)
    dummy_entry = _entry_a()

    # Path traversal via ../
    with pytest.raises(ValueError):
        store._path("../evil")

    with pytest.raises(ValueError):
        store.append("../evil", dummy_entry)

    # Slash embedded in name
    with pytest.raises(ValueError):
        store._path("some/slash")

    with pytest.raises(ValueError):
        store.append("some/slash", dummy_entry)

    # Empty string
    with pytest.raises(ValueError):
        store._path("")

    # Special characters
    with pytest.raises(ValueError):
        store._path("bad!id")


# ---------------------------------------------------------------------------
# test_migrate_snapshot_roundtrips_through_reconstruct
# ---------------------------------------------------------------------------


def test_migrate_snapshot_roundtrips_through_reconstruct(tmp_path):
    tool_calls = [{"id": "tc1", "function": {"name": "read_file", "arguments": "{}"}}]

    messages = [
        {"role": "user", "content": "Hello there", "tool_call_id": None, "tool_calls": [], "token_count": 3},
        {
            "role": "assistant",
            "content": "I will read a file",
            "tool_call_id": None,
            "tool_calls": tool_calls,
            "token_count": 10,
        },
        {
            "role": "tool",
            "content": "file contents here",
            "tool_call_id": "tc1",
            "tool_calls": [],
            "token_count": None,
        },
    ]

    now = datetime(2024, 6, 1, 12, 0, 0)
    snapshot = SessionSnapshot(
        session_id="snap-001",
        created_at=datetime(2024, 1, 1, 0, 0, 0),
        updated_at=now,
        turn_count=2,
        cwd="/project",
        config={},
        messages=messages,
        latest_usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        total_usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        active_tools=[],
        mcp_servers=[],
        active_skills=[],
        todos={},
    )

    entries = migrate_snapshot_to_entries(snapshot)

    # reconstruct_messages should return all 3 messages in order
    reconstructed = reconstruct_messages(entries)

    assert len(reconstructed) == 3
    assert reconstructed[0]["role"] == "user"
    assert reconstructed[0]["content"] == "Hello there"
    assert reconstructed[1]["role"] == "assistant"
    assert reconstructed[1]["tool_calls"] == tool_calls
    assert reconstructed[2]["role"] == "tool"
    assert reconstructed[2]["tool_call_id"] == "tc1"
    assert reconstructed[2]["content"] == "file contents here"

    # Now append to store and confirm read_all -> reconstruct gives the same
    store = _make_store(tmp_path)
    sid = "snap-001"
    store.append_many(sid, entries)

    stored_entries = store.read_all(sid)
    assert len(stored_entries) == len(entries)

    stored_reconstructed = store.reconstruct(sid)
    assert len(stored_reconstructed) == 3
    assert stored_reconstructed[0]["role"] == "user"
    assert stored_reconstructed[1]["role"] == "assistant"
    assert stored_reconstructed[1]["tool_calls"] == tool_calls
    assert stored_reconstructed[2]["role"] == "tool"
    assert stored_reconstructed[2]["tool_call_id"] == "tc1"


# ---------------------------------------------------------------------------
# test_chmod_permissions
# ---------------------------------------------------------------------------


@pytest.mark.skipif(platform.system() == "Windows", reason="chmod not applicable on Windows")
def test_chmod_permissions(tmp_path):
    store = _make_store(tmp_path)
    sid = "session-perms"

    store.append(sid, _entry_a())

    file_path = store._path(sid)
    assert file_path.exists()

    mode = os.stat(file_path).st_mode & 0o777
    assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"


# ---------------------------------------------------------------------------
# Additional: list_session_ids and exists
# ---------------------------------------------------------------------------


def test_list_session_ids(tmp_path):
    store = _make_store(tmp_path)

    assert store.list_session_ids() == []

    store.append("session-b", _entry_a())
    store.append("session-a", _entry_a())

    ids = store.list_session_ids()
    assert sorted(ids) == ["session-a", "session-b"]


def test_exists(tmp_path):
    store = _make_store(tmp_path)
    assert not store.exists("new-session")
    store.append("new-session", _entry_a())
    assert store.exists("new-session")


def test_append_many_roundtrip(tmp_path):
    store = _make_store(tmp_path)
    sid = "session-many"

    ea = _entry_a()
    eb = _entry_b()

    store.append_many(sid, [ea, eb])

    result = store.read_all(sid)
    assert len(result) == 2
    assert result[0].to_dict() == ea.to_dict()
    assert result[1].to_dict() == eb.to_dict()
