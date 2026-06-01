from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from click.testing import CliRunner

from agentforge_harness.agent.persistence import PersistenceManager, SessionSnapshot
from agentforge_harness.client.response import TokenUsage
from agentforge_harness.cli.report import (
    build_session_report,
    render_session_html,
    render_session_markdown,
)
from agentforge_harness.cli.run import cli


def _snapshot(session_id: str = "session_report_test", minute: int = 5) -> SessionSnapshot:
    return SessionSnapshot(
        session_id=session_id,
        name="demo",
        created_at=datetime(2026, 1, 1, 10, 0, 0),
        updated_at=datetime(2026, 1, 1, 10, minute, 0),
        turn_count=2,
        cwd="/tmp/project",
        config={"model": {"provider": "openai", "name": "gpt-4o-mini"}},
        messages=[
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "<done>"},
        ],
        latest_usage=TokenUsage(prompt_tokens=3, completion_tokens=4, total_tokens=7),
        total_usage=TokenUsage(prompt_tokens=30, completion_tokens=40, total_tokens=70),
        active_tools=["read_file", "git_diff"],
        mcp_servers=[],
        active_skills=["api-interface-design"],
        todos={"t1": "write tests"},
        event_sequence=5,
        mode="build",
    )


def test_build_session_report_shape():
    report = build_session_report(_snapshot())

    assert report["session_id"] == "session_report_test"
    assert report["model"] == {"provider": "openai", "name": "gpt-4o-mini"}
    assert report["usage"]["total_tokens"] == 70
    assert report["tools"]["count"] == 2
    assert report["todos"]["count"] == 1


def test_render_exports_escape_html():
    snapshot = _snapshot()

    html = render_session_html(snapshot)
    markdown = render_session_markdown(snapshot)

    assert "&lt;done&gt;" in html
    assert "<done>" not in html
    assert '<section class="metrics">' in html
    assert "<summary>User: hello</summary>" in html
    assert "<h2>Usage</h2>" in html
    assert "**User:** hello" in markdown


def test_agentforge_report_json_reads_latest_session(tmp_path: Path):
    persistence = PersistenceManager(data_dir=tmp_path)
    persistence.save_session(_snapshot("older_session", minute=1))
    persistence.save_session(_snapshot("newer_session", minute=9))

    result = CliRunner().invoke(
        cli,
        ["report", "--data-dir", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["session_id"] == "newer_session"
    assert payload["usage"]["total_tokens"] == 70


def test_agentforge_report_missing_session_exits_nonzero(tmp_path: Path):
    result = CliRunner().invoke(
        cli,
        ["report", "--data-dir", str(tmp_path), "--session-id", "missing"],
    )

    assert result.exit_code == 1
    assert "Session not found" in result.output
