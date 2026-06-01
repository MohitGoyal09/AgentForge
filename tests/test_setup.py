from __future__ import annotations

import stat
from pathlib import Path

from click.testing import CliRunner

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from agentforge_harness.cli.run import cli
from agentforge_harness.cli.setup import _write_config_file, _write_env_file


def test_setup_config_writes_top_level_approval(tmp_path: Path):
    config_path = tmp_path / "config.toml"

    _write_config_file(
        config_path=config_path,
        provider="openai",
        model="gpt-4o-mini",
        base_url="",
    )

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))

    assert data["approval"] == "on-request"
    assert data["model"] == {
        "provider": "openai",
        "name": "gpt-4o-mini",
    }
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600


def test_setup_env_file_is_private(tmp_path: Path):
    env_path = tmp_path / ".env"

    _write_env_file(
        env_path=env_path,
        provider="openai",
        api_key="sk-test",
        base_url="",
    )

    assert "OPENAI_API_KEY=sk-test" in env_path.read_text(encoding="utf-8")
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600


def test_setup_config_writes_custom_base_url(tmp_path: Path):
    config_path = tmp_path / "config.toml"

    _write_config_file(
        config_path=config_path,
        provider="custom",
        model="local/model",
        base_url="http://localhost:11434/v1",
    )

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))

    assert data["model"]["base_url"] == "http://localhost:11434/v1"


def test_agentforge_init_smoke_writes_provider_files(monkeypatch, tmp_path: Path):
    config_dir = tmp_path / "agentforge-config"
    monkeypatch.setattr("agentforge_harness.cli.setup.get_config_dir", lambda: config_dir)
    monkeypatch.setattr("getpass.getpass", lambda prompt="", stream=None: "sk-openai-test")

    result = CliRunner().invoke(
        cli,
        ["init"],
        input="openai\n\n\nn\n",
    )

    assert result.exit_code == 0
    assert "Setup complete" in result.output

    env_text = (config_dir / ".env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-openai-test" in env_text
    assert "OPENAI_BASE_URL" not in env_text

    config = tomllib.loads((config_dir / "config.toml").read_text(encoding="utf-8"))
    assert config["approval"] == "on-request"
    assert config["model"]["provider"] == "openai"
    assert config["model"]["name"] == "gpt-4o-mini"
    assert "base_url" not in config["model"]


def test_agentforge_init_cancel_preserves_existing_files(monkeypatch, tmp_path: Path):
    config_dir = tmp_path / "agentforge-config"
    config_dir.mkdir()
    env_path = config_dir / ".env"
    config_path = config_dir / "config.toml"
    env_path.write_text("OPENAI_API_KEY=old\n", encoding="utf-8")
    config_path.write_text('approval = "auto"\n', encoding="utf-8")
    monkeypatch.setattr("agentforge_harness.cli.setup.get_config_dir", lambda: config_dir)

    result = CliRunner().invoke(cli, ["init"], input="n\n")

    assert result.exit_code == 1
    assert "Setup cancelled" in result.output
    assert env_path.read_text(encoding="utf-8") == "OPENAI_API_KEY=old\n"
    assert config_path.read_text(encoding="utf-8") == 'approval = "auto"\n'


def test_agentforge_init_overwrites_existing_files_when_confirmed(monkeypatch, tmp_path: Path):
    config_dir = tmp_path / "agentforge-config"
    config_dir.mkdir()
    (config_dir / ".env").write_text("OPENAI_API_KEY=old\n", encoding="utf-8")
    (config_dir / "config.toml").write_text('approval = "auto"\n', encoding="utf-8")
    monkeypatch.setattr("agentforge_harness.cli.setup.get_config_dir", lambda: config_dir)
    monkeypatch.setattr("getpass.getpass", lambda prompt="", stream=None: "sk-custom-test")

    result = CliRunner().invoke(
        cli,
        ["init"],
        input="y\ncustom\n\nlocal/model\nn\n",
    )

    assert result.exit_code == 0
    assert "custom settings" in result.output
    env_text = (config_dir / ".env").read_text(encoding="utf-8")
    assert "API_KEY=sk-custom-test" in env_text
    assert "BASE_URL=http://localhost:11434/v1" in env_text
