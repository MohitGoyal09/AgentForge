from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from client.response import TokenUsage
from agent.persistence import PersistenceManager, SessionSnapshot


SAMPLE_SNAPSHOT = SessionSnapshot(
    session_id="test_session_123",
    created_at=datetime(2025, 1, 1, 12, 0, 0),
    updated_at=datetime(2025, 1, 1, 12, 30, 0),
    turn_count=5,
    cwd="/tmp",
    config={},
    messages=[{"role": "user", "content": "hello"}],
    latest_usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
    total_usage=TokenUsage(prompt_tokens=100, completion_tokens=200, total_tokens=300),
    active_tools=["read_file", "shell"],
    mcp_servers=[],
    active_skills=[],
    todos={},
    event_sequence=12,
    mode="build",
)


class TestSessionSnapshot:
    def test_to_dict_roundtrip(self):
        d = SAMPLE_SNAPSHOT.to_dict()
        restored = SessionSnapshot.from_dict(d)
        assert restored.session_id == "test_session_123"
        assert restored.turn_count == 5
        assert restored.latest_usage.prompt_tokens == 10
        assert restored.total_usage.completion_tokens == 200
        assert restored.messages == [{"role": "user", "content": "hello"}]
        assert restored.mode == "build"

    def test_from_dict_handles_missing_fields(self):
        d = {
            "session_id": "s1",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T01:00:00",
            "turn_count": 3,
            "messages": [],
            "total_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }
        restored = SessionSnapshot.from_dict(d)
        assert restored.cwd == ""
        assert restored.active_tools == []
        assert restored.mode == "build"

    def test_schema_version_default(self):
        assert SAMPLE_SNAPSHOT.schema_version == 1


class TestPersistenceManager:
    def test_save_and_load_session(self, tmp_path: Path):
        pm = PersistenceManager(data_dir=tmp_path)
        pm.save_session(SAMPLE_SNAPSHOT)
        loaded = pm.load_session("test_session_123")
        assert loaded is not None
        assert loaded.session_id == "test_session_123"
        assert loaded.turn_count == 5

    def test_load_nonexistent_session_returns_none(self, tmp_path: Path):
        pm = PersistenceManager(data_dir=tmp_path)
        assert pm.load_session("no_such_session") is None

    def test_list_sessions(self, tmp_path: Path):
        pm = PersistenceManager(data_dir=tmp_path)
        s2 = SessionSnapshot(
            session_id="session_b",
            created_at=datetime(2025, 1, 2),
            updated_at=datetime(2025, 1, 2),
            turn_count=1,
            cwd="/tmp",
            config={},
            messages=[],
            latest_usage=TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            total_usage=TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            active_tools=[],
            mcp_servers=[],
            active_skills=[],
            todos={},
        )
        pm.save_session(SAMPLE_SNAPSHOT)
        pm.save_session(s2)
        sessions = pm.list_sessions()
        assert len(sessions) == 2
        ids = [s["session_id"] for s in sessions]
        assert "test_session_123" in ids
        assert "session_b" in ids

    def test_save_and_load_checkpoint(self, tmp_path: Path):
        pm = PersistenceManager(data_dir=tmp_path)
        cid = pm.save_checkpoint(SAMPLE_SNAPSHOT)
        assert "test_session_123" in cid

        loaded = pm.load_checkpoint(cid)
        assert loaded is not None
        assert loaded.session_id == "test_session_123"

    def test_load_nonexistent_checkpoint_returns_none(self, tmp_path: Path):
        pm = PersistenceManager(data_dir=tmp_path)
        assert pm.load_checkpoint("no_such_checkpoint") is None

    def test_list_checkpoints(self, tmp_path: Path):
        pm = PersistenceManager(data_dir=tmp_path)
        pm.save_checkpoint(SAMPLE_SNAPSHOT)
        checkpoints = pm.list_checkpoints()
        assert len(checkpoints) == 1
        assert checkpoints[0]["session_id"] == "test_session_123"

    def test_append_and_load_events(self, tmp_path: Path):
        pm = PersistenceManager(data_dir=tmp_path)
        pm.append_event("test_session_123", turn=1, sequence=1, event_type="tool_call", payload={"tool": "read_file"})
        pm.append_event("test_session_123", turn=1, sequence=2, event_type="response", payload={"text": "hello"})

        events_path = tmp_path / "events" / "test_session_123.jsonl"
        assert events_path.exists()
        lines = events_path.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["type"] == "tool_call"

    def test_invalid_session_id_raises_error(self, tmp_path: Path):
        pm = PersistenceManager(data_dir=tmp_path)
        import re
        with pytest.raises(ValueError, match="Invalid"):
            pm.load_session("../bad")

    def test_directory_permissions(self, tmp_path: Path):
        pm = PersistenceManager(data_dir=tmp_path)
        assert pm.sessions_dir.exists()
        assert pm.checkpoints_dir.exists()
        assert pm.events_dir.exists()
