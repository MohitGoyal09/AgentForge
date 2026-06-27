"""Tests for per-run UUID and JSONL diagnostics."""
from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentforge_harness.agent.events import AgentEventType, AgentStartEvent, AgentEndEvent
from agentforge_harness.agent.persistence import PersistenceManager


# ---------------------------------------------------------------------------
# run_id UUID tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_id_is_valid_uuid():
    """The run_id attached to the start event is a valid UUID string."""
    from agentforge_harness.agent.agent import Agent
    from agentforge_harness.agent.events import AgentEventType

    config = MagicMock()
    config.max_turns = 1
    config.model_name = "test-model"
    config.model.fallbacks = []
    config.redaction_enabled = False
    config.cwd = Path(".")

    agent = Agent.__new__(Agent)
    agent.config = config
    agent._record_events = False

    session = MagicMock()
    session._running = False
    session.cancel_requested = False
    session._turn_count = 0
    session._steering_queue = MagicMock()
    session._steering_queue.clear = MagicMock()
    session.reset_cancel = MagicMock()
    session.hook_system = MagicMock()
    session.hook_system.trigger_before_agent = AsyncMock()
    session.hook_system.trigger_after_agent = AsyncMock()
    session.context_manager = MagicMock()
    session.context_manager.add_user_message = MagicMock()
    session.loop_detector = MagicMock()
    session.loop_detector.clear = MagicMock()

    agent.session = session

    # Patch _agentic_loop to yield nothing (immediate return)
    async def _empty_loop():
        return
        yield  # make it an async generator

    run_id_seen = None

    events = []
    with patch.object(agent, "_agentic_loop", return_value=_empty_loop()):
        async for event in agent.run("hello"):
            events.append(event)

    start_events = [e for e in events if e.type == AgentEventType.AGENT_START]
    assert len(start_events) == 1
    start = start_events[0]
    assert isinstance(start, AgentStartEvent)
    run_id = start.run_id
    assert run_id is not None
    # Must be parseable as a UUID
    parsed = uuid.UUID(run_id)
    assert str(parsed) == run_id


@pytest.mark.asyncio
async def test_consecutive_runs_have_different_run_ids():
    """Two consecutive run() calls produce different run_ids."""
    from agentforge_harness.agent.agent import Agent
    from agentforge_harness.agent.events import AgentEventType

    config = MagicMock()
    config.max_turns = 1
    config.model_name = "test-model"
    config.model.fallbacks = []
    config.redaction_enabled = False
    config.cwd = Path(".")

    agent = Agent.__new__(Agent)
    agent.config = config
    agent._record_events = False

    session = MagicMock()
    session._running = False
    session.cancel_requested = False
    session._turn_count = 0
    session._steering_queue = MagicMock()
    session._steering_queue.clear = MagicMock()
    session.reset_cancel = MagicMock()
    session.hook_system = MagicMock()
    session.hook_system.trigger_before_agent = AsyncMock()
    session.hook_system.trigger_after_agent = AsyncMock()
    session.context_manager = MagicMock()
    session.context_manager.add_user_message = MagicMock()
    session.loop_detector = MagicMock()
    session.loop_detector.clear = MagicMock()

    agent.session = session

    async def _empty_loop():
        return
        yield

    run_ids = []

    for _ in range(2):
        with patch.object(agent, "_agentic_loop", return_value=_empty_loop()):
            async for event in agent.run("hello"):
                if event.type == AgentEventType.AGENT_START:
                    run_ids.append(event.run_id)

    assert len(run_ids) == 2
    assert run_ids[0] != run_ids[1]


# ---------------------------------------------------------------------------
# append_run_diagnostic tests
# ---------------------------------------------------------------------------

def test_append_run_diagnostic_creates_file_and_appends_json():
    """append_run_diagnostic writes valid JSON lines to the .jsonl file."""
    with tempfile.TemporaryDirectory() as tmp:
        pm = PersistenceManager(data_dir=Path(tmp))
        session_id = "test-session-01"
        record1 = {"run_id": "abc", "status": "ok"}
        record2 = {"run_id": "xyz", "status": "done"}

        pm.append_run_diagnostic(session_id, record1)
        pm.append_run_diagnostic(session_id, record2)

        jsonl_path = pm.sessions_dir / f"{session_id}-runs.jsonl"
        assert jsonl_path.exists()

        lines = jsonl_path.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0]) == record1
        assert json.loads(lines[1]) == record2


def test_append_run_diagnostic_invalid_session_id_raises():
    """append_run_diagnostic raises ValueError for invalid session_id."""
    with tempfile.TemporaryDirectory() as tmp:
        pm = PersistenceManager(data_dir=Path(tmp))
        with pytest.raises(ValueError):
            pm.append_run_diagnostic("../evil/path", {"x": 1})


def test_append_run_diagnostic_does_not_raise_on_write_error(caplog):
    """append_run_diagnostic logs a WARNING but does not raise on I/O failure."""
    import logging
    with tempfile.TemporaryDirectory() as tmp:
        pm = PersistenceManager(data_dir=Path(tmp))
        # Make sessions_dir read-only to cause a write failure
        pm.sessions_dir.chmod(0o500)
        try:
            with caplog.at_level(logging.WARNING):
                pm.append_run_diagnostic("session-123", {"x": 1})
            # Should not raise
            assert any("Failed" in r.message or "failed" in r.message for r in caplog.records)
        finally:
            pm.sessions_dir.chmod(0o700)


def test_start_event_data_includes_run_id():
    """AgentStartEvent.data contains the run_id."""
    event = AgentStartEvent(message="hi", run_id="test-run-id")
    assert event.data["run_id"] == "test-run-id"


def test_end_event_data_includes_run_id():
    """AgentEndEvent.data contains the run_id."""
    event = AgentEndEvent(response="done", run_id="test-run-id")
    assert event.data["run_id"] == "test-run-id"
