from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_core import ValidationError
from agentforge_harness.config.config import Config, ModelConfig, ModelProvider
from agentforge_harness.config.loader import _get_agent_md_files


class TestConfigValidation:
    def test_valid_config_passes(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test-key")
        cfg = Config(cwd=Path("/tmp"))
        cfg.model_name = "openai/gpt-4o-mini"
        errors = cfg.validate()
        assert len(errors) == 0

    def test_missing_model_name_returns_error(self):
        cfg = Config(cwd=Path("/tmp"))
        cfg.model_name = ""
        errors = cfg.validate()
        assert any("model name" in e.lower() for e in errors)

    def test_provider_native_model_name_without_slash_is_valid(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        cfg = Config(cwd=Path("/tmp"))
        cfg.model = ModelConfig(provider=ModelProvider.OPENAI, name="gpt-4o")
        errors = cfg.validate()
        assert len(errors) == 0

    def test_invalid_temperature_returns_error(self):
        with pytest.raises(ValidationError, match="temperature"):
            ModelConfig(temperature=3.0)

    def test_negative_temperature_returns_error(self):
        with pytest.raises(ValidationError, match="temperature"):
            ModelConfig(temperature=-1)

    def test_nonexistent_cwd_returns_error(self):
        cfg = Config(
            cwd=Path("/nonexistent/path/xyz123"),
        )
        cfg.model_name = "openai/gpt-4o"
        errors = cfg.validate()
        assert any("working directory" in e.lower() or "does not exist" in e.lower() for e in errors)


class TestConfigModelName:
    def test_model_name_property(self):
        cfg = Config(cwd=Path("/tmp"))
        cfg.model_name = "anthropic/claude-sonnet-4"
        assert cfg.model_name == "anthropic/claude-sonnet-4"

    def test_set_model_name(self):
        cfg = Config(cwd=Path("/tmp"))
        cfg.model_name = "openai/gpt-4o"
        cfg.model_name = "google/gemini-pro"
        assert cfg.model_name == "google/gemini-pro"


class TestConfigAPIKey:
    def test_openrouter_api_key_from_env(self, monkeypatch):
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test-key")
        cfg = Config(cwd=Path("/tmp"))
        cfg.model_name = "openai/gpt-4o"
        assert cfg.api_key == "sk-or-v1-test-key"

    def test_provider_specific_key_wins_over_generic_api_key(self, monkeypatch):
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.setenv("API_KEY", "sk-api-key")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-key")
        cfg = Config(cwd=Path("/tmp"))
        cfg.model_name = "openai/gpt-4o"
        assert cfg.api_key == "sk-or-v1-key"

    def test_openai_provider_uses_openai_key(self, monkeypatch):
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-key")
        cfg = Config(cwd=Path("/tmp"), model=ModelConfig(provider=ModelProvider.OPENAI, name="gpt-4o"))
        assert cfg.api_key == "sk-openai"

    def test_anthropic_provider_uses_anthropic_key(self, monkeypatch):
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        cfg = Config(
            cwd=Path("/tmp"),
            model=ModelConfig(provider=ModelProvider.ANTHROPIC, name="claude-3-5-sonnet-latest"),
        )
        assert cfg.api_key == "sk-ant"

    def test_base_url_defaults_to_openrouter(self, monkeypatch):
        monkeypatch.delenv("BASE_URL", raising=False)
        monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)
        cfg = Config(cwd=Path("/tmp"))
        cfg.model_name = "openai/gpt-4o"
        assert cfg.base_url == "https://openrouter.ai/api/v1"

    def test_provider_specific_base_url_wins_over_generic_base_url(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)
        monkeypatch.setenv("BASE_URL", "https://api.example.com/v1")
        monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/v1")
        cfg = Config(cwd=Path("/tmp"))
        cfg.model_name = "openai/gpt-4o"
        assert cfg.base_url == "https://openrouter.ai/v1"

    def test_model_base_url_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/v1")
        cfg = Config(
            cwd=Path("/tmp"),
            model=ModelConfig(base_url="https://configured.example/v1"),
        )
        assert cfg.base_url == "https://configured.example/v1"

    def test_custom_provider_requires_base_url(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "sk-custom")
        monkeypatch.delenv("BASE_URL", raising=False)
        cfg = Config(cwd=Path("/tmp"), model=ModelConfig(provider=ModelProvider.CUSTOM, name="local/model"))
        errors = cfg.validate()
        assert any("custom provider" in e.lower() for e in errors)


class TestAgentInstructions:
    def test_agents_md_is_loaded(self, tmp_path: Path):
        (tmp_path / "AGENTS.md").write_text("Use project instructions.", encoding="utf-8")

        assert _get_agent_md_files(tmp_path) == "Use project instructions."

    def test_agents_md_preferred_over_agent_md(self, tmp_path: Path):
        (tmp_path / "AGENTS.md").write_text("plural", encoding="utf-8")
        (tmp_path / "AGENT.MD").write_text("singular", encoding="utf-8")

        assert _get_agent_md_files(tmp_path) == "plural"
