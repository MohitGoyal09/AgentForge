from __future__ import annotations

import json
from pathlib import Path
import os
import subprocess

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


def test_doctor_warns_for_permissive_workspace_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("agentforge_harness.cli.doctor.get_data_dir", lambda: tmp_path / "data")
    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")
    os.chmod(env_path, 0o644)

    config = Config(
        cwd=tmp_path,
        model=ModelConfig(provider=ModelProvider.OPENAI, name="gpt-4o-mini"),
    )

    statuses = _statuses(build_doctor_report(config))

    assert statuses["safety.env.permissions"] == "warn"
    assert statuses["safety.env.git"] == "ok"
    assert statuses["safety.env.gitignore"] == "warn"


def test_doctor_errors_when_workspace_env_is_tracked(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("agentforge_harness.cli.doctor.get_data_dir", lambda: tmp_path / "data")
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, stdout=subprocess.DEVNULL)
    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")
    os.chmod(env_path, 0o600)
    subprocess.run(["git", "add", ".env"], cwd=tmp_path, check=True, stdout=subprocess.DEVNULL)

    config = Config(
        cwd=tmp_path,
        model=ModelConfig(provider=ModelProvider.OPENAI, name="gpt-4o-mini"),
    )

    report = build_doctor_report(config)
    statuses = _statuses(report)

    assert report.has_errors
    assert statuses["safety.env.permissions"] == "ok"
    assert statuses["safety.env.git"] == "error"


def test_doctor_reports_config_file_permissions(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("agentforge_harness.cli.doctor.get_data_dir", lambda: tmp_path / "data")
    config_path = tmp_path / "config.toml"
    config_path.write_text('approval = "on-request"\n', encoding="utf-8")
    os.chmod(config_path, 0o644)
    monkeypatch.setattr("agentforge_harness.cli.doctor.get_system_config_path", lambda: config_path)

    config = Config(
        cwd=tmp_path,
        model=ModelConfig(provider=ModelProvider.OPENAI, name="gpt-4o-mini"),
    )

    statuses = _statuses(build_doctor_report(config))

    assert statuses["config.system"] == "warn"


def test_doctor_ok_when_env_is_gitignored(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("agentforge_harness.cli.doctor.get_data_dir", lambda: tmp_path / "data")
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, stdout=subprocess.DEVNULL)
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")
    os.chmod(env_path, 0o600)

    config = Config(
        cwd=tmp_path,
        model=ModelConfig(provider=ModelProvider.OPENAI, name="gpt-4o-mini"),
    )

    statuses = _statuses(build_doctor_report(config))

    assert statuses["safety.env.gitignore"] == "ok"


def test_doctor_warns_for_mcp_cwd_outside_workspace(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("agentforge_harness.cli.doctor.get_data_dir", lambda: tmp_path / "data")
    outside = tmp_path.parent / "outside-mcp"
    outside.mkdir(exist_ok=True)
    config = Config(
        cwd=tmp_path,
        model=ModelConfig(provider=ModelProvider.OPENAI, name="gpt-4o-mini"),
        mcp_servers={
            "outside": MCPServerConfig(command="python3", cwd=outside),
        },
    )

    statuses = _statuses(build_doctor_report(config))

    assert statuses["paths.mcp.outside"] == "warn"


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
