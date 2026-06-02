from __future__ import annotations

import io
import json
from pathlib import Path
import os
import subprocess

from click.testing import CliRunner
from rich.console import Console

from agentforge_harness.cli.doctor import build_doctor_report, print_doctor_report
from agentforge_harness.cli.run import cli
from agentforge_harness.config.config import (
    ApprovalPolicy,
    Config,
    MCPServerConfig,
    ModelConfig,
    ModelProvider,
)
from agentforge_harness.ui.tui import AGENT_THEME


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


def test_doctor_human_output_is_grouped_and_actionable(monkeypatch, tmp_path: Path):
    for env_name in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "API_KEY"):
        monkeypatch.setenv(env_name, "")
    monkeypatch.setattr("agentforge_harness.cli.doctor.get_data_dir", lambda: tmp_path / "data")
    output = io.StringIO()
    console = Console(file=output, theme=AGENT_THEME, width=100, color_system=None)

    report = build_doctor_report(Config(cwd=tmp_path))
    print_doctor_report(report, console=console)

    rendered = output.getvalue()
    assert "AgentForge is not ready yet." in rendered
    assert "Setup" in rendered
    assert "Provider" in rendered
    assert "fix: Run agentforge init" in rendered
    assert "detail:" in rendered
    assert "Status" not in rendered
    assert "Doctor Checks" not in rendered


def test_doctor_human_output_shows_setup_source(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("agentforge_harness.cli.doctor.get_data_dir", lambda: tmp_path / "data")
    config_path = tmp_path / "config.toml"
    config_path.write_text('approval = "on-request"\n', encoding="utf-8")
    monkeypatch.setattr("agentforge_harness.cli.doctor.get_system_config_path", lambda: config_path)
    output = io.StringIO()
    console = Console(file=output, theme=AGENT_THEME, width=120, color_system=None)

    report = build_doctor_report(
        Config(
            cwd=tmp_path,
            model=ModelConfig(provider=ModelProvider.OPENAI, name="gpt-4o-mini"),
        )
    )
    print_doctor_report(report, console=console)

    rendered = output.getvalue()
    assert "Setup source: user config" in rendered
    assert "config.toml" in rendered


def test_doctor_human_output_shows_defaults_when_no_config_file(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setattr("agentforge_harness.cli.doctor.get_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(
        "agentforge_harness.cli.doctor.get_system_config_path",
        lambda: tmp_path / "missing-config.toml",
    )
    output = io.StringIO()
    console = Console(file=output, theme=AGENT_THEME, width=120, color_system=None)

    report = build_doctor_report(Config(cwd=tmp_path))
    print_doctor_report(report, console=console)

    rendered = output.getvalue()
    assert "Setup source: no saved config" in rendered
    assert "Run agentforge init" in rendered


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
    assert any("MCP servers can run external commands" in check.message for check in report.checks)
    assert any("local user permissions" in check.detail for check in report.checks)


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


def test_doctor_warns_when_workspace_env_is_not_gitignored(monkeypatch, tmp_path: Path):
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

    assert "safety.env.permissions" not in statuses
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
    assert "safety.env.permissions" not in statuses
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


def test_doctor_detects_project_config_without_permission_warning(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("agentforge_harness.cli.doctor.get_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(
        "agentforge_harness.cli.doctor.get_system_config_path",
        lambda: tmp_path / "missing-system-config.toml",
    )
    project_config = tmp_path / ".agentforge" / "config.toml"
    project_config.parent.mkdir()
    project_config.write_text('approval = "on-request"\n', encoding="utf-8")
    os.chmod(project_config, 0o644)

    config = Config(
        cwd=tmp_path,
        model=ModelConfig(provider=ModelProvider.OPENAI, name="gpt-4o-mini"),
    )

    statuses = _statuses(build_doctor_report(config))

    assert statuses["config.project"] == "ok"
    assert "config.files" not in statuses


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
