from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_core import ValidationError
from config.config import Config, ModelConfig


class TestConfigValidation:
    def test_valid_config_passes(self):
        cfg = Config(cwd=Path("/tmp"))
        cfg.model_name = "openai/gpt-4o-mini"
        errors = cfg.validate()
        assert len(errors) == 0

    def test_missing_model_name_returns_error(self):
        cfg = Config(cwd=Path("/tmp"))
        cfg.model_name = ""
        errors = cfg.validate()
        assert any("model name" in e.lower() for e in errors)

    def test_model_name_without_slash_returns_error(self):
        cfg = Config(cwd=Path("/tmp"))
        cfg.model_name = "gpt-4o"
        errors = cfg.validate()
        assert any("model name" in e.lower() for e in errors)

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
    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test-key")
        cfg = Config(cwd=Path("/tmp"))
        cfg.model_name = "openai/gpt-4o"
        assert cfg.api_key == "sk-or-v1-test-key"

    def test_api_key_prefers_api_key_over_openrouter(self, monkeypatch):
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.setenv("API_KEY", "sk-api-key")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-key")
        cfg = Config(cwd=Path("/tmp"))
        cfg.model_name = "openai/gpt-4o"
        assert cfg.api_key == "sk-api-key"

    def test_base_url_defaults_to_openrouter(self, monkeypatch):
        monkeypatch.delenv("BASE_URL", raising=False)
        monkeypatch.setenv("OPENROUTER_BASE_URL", "https://custom.openrouter.ai/v1")
        cfg = Config(cwd=Path("/tmp"))
        cfg.model_name = "openai/gpt-4o"
        assert cfg.base_url == "https://custom.openrouter.ai/v1"

    def test_base_url_prefers_base_url(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)
        monkeypatch.setenv("BASE_URL", "https://api.example.com/v1")
        monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/v1")
        cfg = Config(cwd=Path("/tmp"))
        cfg.model_name = "openai/gpt-4o"
        assert cfg.base_url == "https://api.example.com/v1"
