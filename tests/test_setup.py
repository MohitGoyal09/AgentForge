from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from agentforge_harness.cli.setup import _write_config_file


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
