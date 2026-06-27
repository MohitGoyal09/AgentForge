"""Tests for schema_version validation in PersistenceManager.load_session()."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from agentforge_harness.agent.persistence import PersistenceManager, SCHEMA_VERSION, SessionSnapshot
from agentforge_harness.client.response import TokenUsage


def _minimal_session_dict(
    session_id: str = "test-session-01",
    schema_version: int | None = SCHEMA_VERSION,
) -> dict:
    base = {
        "session_id": session_id,
        "name": "test",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "turn_count": 0,
        "cwd": "/tmp",
        "config": {},
        "messages": [],
        "latest_usage": {},
        "total_usage": {},
        "active_tools": [],
        "mcp_servers": [],
        "active_skills": [],
        "todos": {},
        "event_sequence": 0,
        "mode": "build",
    }
    if schema_version is not None:
        base["schema_version"] = schema_version
    return base


def _write_session(pm: PersistenceManager, data: dict) -> None:
    session_id = data["session_id"]
    file_path = pm.sessions_dir / f"{session_id}.json"
    file_path.write_text(json.dumps(data))


def test_matching_schema_version_loads_successfully():
    """Session with schema_version == SCHEMA_VERSION loads without error."""
    with tempfile.TemporaryDirectory() as tmp:
        pm = PersistenceManager(data_dir=Path(tmp))
        data = _minimal_session_dict(schema_version=SCHEMA_VERSION)
        _write_session(pm, data)
        snapshot = pm.load_session("test-session-01")
    assert snapshot is not None
    assert snapshot.session_id == "test-session-01"


def test_future_schema_version_raises_value_error():
    """Session with schema_version > SCHEMA_VERSION raises ValueError."""
    with tempfile.TemporaryDirectory() as tmp:
        pm = PersistenceManager(data_dir=Path(tmp))
        data = _minimal_session_dict(schema_version=SCHEMA_VERSION + 1)
        _write_session(pm, data)
        with pytest.raises(ValueError, match="schema version"):
            pm.load_session("test-session-01")


def test_future_schema_version_error_message_is_informative():
    """ValueError for future schema includes the version numbers."""
    with tempfile.TemporaryDirectory() as tmp:
        pm = PersistenceManager(data_dir=Path(tmp))
        future_version = SCHEMA_VERSION + 5
        data = _minimal_session_dict(schema_version=future_version)
        _write_session(pm, data)
        with pytest.raises(ValueError) as exc_info:
            pm.load_session("test-session-01")
    msg = str(exc_info.value)
    assert str(future_version) in msg
    assert str(SCHEMA_VERSION) in msg


def test_older_schema_version_loads_successfully():
    """Session with schema_version < SCHEMA_VERSION (old session) loads fine."""
    with tempfile.TemporaryDirectory() as tmp:
        pm = PersistenceManager(data_dir=Path(tmp))
        data = _minimal_session_dict(schema_version=0)
        _write_session(pm, data)
        snapshot = pm.load_session("test-session-01")
    assert snapshot is not None


def test_missing_schema_version_key_loads_successfully():
    """Session with no schema_version key (treated as 0) loads without error."""
    with tempfile.TemporaryDirectory() as tmp:
        pm = PersistenceManager(data_dir=Path(tmp))
        # Pass None so the key is omitted entirely
        data = _minimal_session_dict(schema_version=None)
        _write_session(pm, data)
        snapshot = pm.load_session("test-session-01")
    assert snapshot is not None
