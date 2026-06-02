from __future__ import annotations

from pathlib import Path

from agentforge_harness.cli.models import ModelOption, list_models_for_config
from agentforge_harness.config.config import Config, ModelConfig, ModelProvider


async def test_list_models_for_config_uses_curated_openai_suggestions():
    config = Config(
        cwd=Path("/tmp"),
        model=ModelConfig(provider=ModelProvider.OPENAI, name="gpt-4o-mini"),
    )

    result = await list_models_for_config(config)

    assert result.provider == "openai"
    assert result.current_model == "gpt-4o-mini"
    assert result.live is False
    assert result.models[0].name == "gpt-4o-mini"
    assert any(model.name == "gpt-4o" for model in result.models)


async def test_list_models_for_config_falls_back_when_live_fetch_fails(monkeypatch):
    config = Config(
        cwd=Path("/tmp"),
        model=ModelConfig(provider=ModelProvider.OPENROUTER, name="openrouter/free"),
    )

    async def fail_fetch(config: Config, limit: int) -> list[ModelOption]:
        raise RuntimeError("network unavailable")

    monkeypatch.setattr("agentforge_harness.cli.models._fetch_openai_compatible_models", fail_fetch)

    result = await list_models_for_config(config)

    assert result.provider == "openrouter"
    assert result.live is False
    assert "network unavailable" in result.message
    assert result.models[0].name == "openrouter/free"


async def test_list_models_for_config_uses_live_models_when_available(monkeypatch):
    config = Config(
        cwd=Path("/tmp"),
        model=ModelConfig(provider=ModelProvider.OPENROUTER, name="openrouter/free"),
    )

    async def fetch(config: Config, limit: int) -> list[ModelOption]:
        return [
            ModelOption("z/model", "live"),
            ModelOption("a/model", "live"),
        ]

    monkeypatch.setattr("agentforge_harness.cli.models._fetch_openai_compatible_models", fetch)

    result = await list_models_for_config(config)

    assert result.live is True
    assert result.models == [
        ModelOption("openrouter/free", "current"),
        ModelOption("z/model", "live"),
        ModelOption("a/model", "live"),
    ]
