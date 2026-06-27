from __future__ import annotations
import pytest
from pathlib import Path
from agentforge_harness.agent.persistence import PersistenceManager
from agentforge_harness.agent.session import Session
from agentforge_harness.config.config import Config


async def _make_session(tmp_path: Path) -> Session:
    config = Config(cwd=tmp_path, model_name="test/model")
    session = Session(config=config, persistence=PersistenceManager(data_dir=tmp_path))
    await session.initialize()
    return session


@pytest.mark.asyncio
async def test_prompt_follow_up_enqueues(tmp_path):
    session = await _make_session(tmp_path)
    session.prompt("hello", "follow_up")
    assert session.pop_latest_follow_up_message() == "hello"


@pytest.mark.asyncio
async def test_prompt_steer_enqueues(tmp_path):
    session = await _make_session(tmp_path)
    session.prompt("pivot now", "steer")
    assert session._steering_queue.pop_steer() == "pivot now"


@pytest.mark.asyncio
async def test_prompt_default_mode_is_follow_up(tmp_path):
    session = await _make_session(tmp_path)
    session.prompt("default msg")
    assert session.pop_latest_follow_up_message() == "default msg"


@pytest.mark.asyncio
async def test_pop_follow_up_returns_none_when_empty(tmp_path):
    session = await _make_session(tmp_path)
    assert session.pop_latest_follow_up_message() is None


@pytest.mark.asyncio
async def test_reset_clears_steering_queue(tmp_path):
    session = await _make_session(tmp_path)
    session.prompt("queued", "steer")
    session.prompt("also queued", "follow_up")
    session.reset()
    assert session.pop_latest_follow_up_message() is None
    assert session._steering_queue.pop_steer() is None


@pytest.mark.asyncio
async def test_queue_update_event_emitted_for_steer(tmp_path):
    """QUEUE_UPDATE event is yielded when a steer is drained between tool batches."""
    session_obj = await _make_session(tmp_path)
    session_obj.prompt("focus on security", "steer")
    assert session_obj._steering_queue.snapshot()["steer"] == ["focus on security"]
    session_obj._steering_queue.clear()
    assert session_obj._steering_queue.pop_steer() is None
