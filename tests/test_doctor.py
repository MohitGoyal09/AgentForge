from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from agentforge_harness.cli.doctor import build_doctor_report
from agentforge_harness.cli.run import cli
from agentforge_harness.config.config import (
    ApprovalPolicy,
    Config,
    MCPServerConfig,
    ModelConfig,
    ModelProvider,
)


def _statuses(report):
    return {check.name: check.status for check in report.checks}


def test_doctor_reports_ready_config(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("agentforge_harness.cli.doctor.get_data_dir", lambda: tmp_path / "data")
    skill_root = tmp_path / ".agentforge" / "skills"
    skill_root.mkdir(parents=True)

    config = Config(
        cwd=tmp_path,
        model=ModelConfig(provider=ModelProvider.OPENAI, name="gpt-4o-mini"),
        skill_roots=[skill_root],
    )

    report = build_doctor_report(config)
    statuses = _statuses(report)

    assert not report.has_errors
    assert statuses["config"] == "ok"
    assert statuses["provider.key"] == "ok"
    assert statuses["data_dir"] == "ok"
    assert statuses["skills.roots"] == "ok"
    assert statuses["safety.redaction"] == "ok"


def test_doctor_reports_missing_api_key(monkeypatch, tmp_path: Path):
    for env_name in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "API_KEY"):
        monkeypatch.setenv(env_name, "")
    monkeypatch.setattr("agentforge_harness.cli.doctor.get_data_dir", lambda: tmp_path / "data")

    report = build_doctor_report(Config(cwd=tmp_path))

    assert report.has_errors
    assert _statuses(report)["provider.key"] == "error"
    assert any("No API key found" in check.message for check in report.checks)


def test_doctor_reports_mcp_trust_warning_and_missing_command(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("agentforge_harness.cli.doctor.get_data_dir", lambda: tmp_path / "data")
    config = Config(
        cwd=tmp_path,
        model=ModelConfig(provider=ModelProvider.OPENAI, name="gpt-4o-mini"),
        mcp_servers={
            "missing": MCPServerConfig(command="definitely-not-agentforge-mcp"),
        },
    )

    report = build_doctor_report(config)
    statuses = _statuses(report)

    assert report.has_errors
    assert statuses["mcp.trust"] == "warn"
    assert statuses["mcp.missing"] == "error"


def test_doctor_warns_for_risky_safety_settings(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("agentforge_harness.cli.doctor.get_data_dir", lambda: tmp_path / "data")
    config = Config(
        cwd=tmp_path,
        model=ModelConfig(provider=ModelProvider.OPENAI, name="gpt-4o-mini"),
        approval=ApprovalPolicy.YOLO,
        redaction_enabled=False,
        output_hygiene_enabled=False,
        prompt_injection_protection_enabled=False,
    )

    statuses = _statuses(build_doctor_report(config))

    assert statuses["safety.approval"] == "warn"
    assert statuses["safety.redaction"] == "warn"
    assert statuses["safety.output_hygiene"] == "warn"
    assert statuses["safety.prompt_injection"] == "warn"


def test_agentforge_doctor_cli_json_smoke(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("agentforge_harness.cli.doctor.get_data_dir", lambda: tmp_path / "data")

    result = CliRunner().invoke(
        cli,
        ["doctor", "--cwd", str(tmp_path), "--json"],
        env={
            "OPENAI_API_KEY": "",
            "OPENROUTER_API_KEY": "sk-or-v1-test",
            "ANTHROPIC_API_KEY": "",
            "API_KEY": "",
        },
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert any(check["name"] == "provider.key" for check in payload["checks"])


def test_agentforge_doctor_cli_fails_on_missing_key(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("agentforge_harness.cli.doctor.get_data_dir", lambda: tmp_path / "data")

    result = CliRunner().invoke(
        cli,
        ["doctor", "--cwd", str(tmp_path), "--json"],
        env={
            "OPENROUTER_API_KEY": "",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "API_KEY": "",
        },
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert "No API key found" in result.output
