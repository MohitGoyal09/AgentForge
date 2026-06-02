from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from agentforge_harness.config.config import Config, ModelProvider


@dataclass(frozen=True)
class ModelOption:
    name: str
    source: str
    note: str = ""


@dataclass(frozen=True)
class ModelList:
    provider: str
    current_model: str
    models: list[ModelOption]
    live: bool
    message: str = ""


CURATED_MODELS: dict[ModelProvider, list[ModelOption]] = {
    ModelProvider.OPENROUTER: [
        ModelOption("openrouter/free", "suggested", "Routes to currently available free models"),
        ModelOption("openai/gpt-4o-mini", "example", "OpenRouter-hosted OpenAI model"),
        ModelOption("anthropic/claude-3.5-sonnet", "example", "OpenRouter-hosted Anthropic model"),
    ],
    ModelProvider.OPENAI: [
        ModelOption("gpt-4o-mini", "suggested", "Fast default OpenAI model"),
        ModelOption("gpt-4o", "example", "Larger general OpenAI model"),
    ],
    ModelProvider.ANTHROPIC: [
        ModelOption("claude-3-5-sonnet-latest", "suggested", "Default Anthropic model"),
        ModelOption("claude-3-5-haiku-latest", "example", "Smaller Anthropic model"),
    ],
    ModelProvider.CUSTOM: [
        ModelOption("local/model", "suggested", "Placeholder for an OpenAI-compatible endpoint"),
        ModelOption("llama3.2", "example", "Common local-server model style"),
        ModelOption("qwen2.5-coder", "example", "Common local coding-model style"),
    ],
}


async def list_models_for_config(config: Config, limit: int = 24) -> ModelList:
    provider = config.provider
    curated = CURATED_MODELS.get(provider, [])

    if _supports_openai_compatible_model_list(config):
        try:
            live_models = await _fetch_openai_compatible_models(config, limit=limit)
        except Exception as e:
            return ModelList(
                provider=provider.value,
                current_model=config.model_name,
                models=_dedupe_models([*curated, ModelOption(config.model_name, "current")]),
                live=False,
                message=f"Live model fetch failed: {_short_error(e)}",
            )

        if live_models:
            return ModelList(
                provider=provider.value,
                current_model=config.model_name,
                models=_dedupe_models(
                    [ModelOption(config.model_name, "current"), *live_models]
                )[:limit],
                live=True,
                message="Live provider model list",
            )

    return ModelList(
        provider=provider.value,
        current_model=config.model_name,
        models=_dedupe_models([ModelOption(config.model_name, "current"), *curated])[:limit],
        live=False,
        message="Curated suggestions",
    )


def _supports_openai_compatible_model_list(config: Config) -> bool:
    if config.provider in {ModelProvider.OPENROUTER, ModelProvider.CUSTOM}:
        return bool(config.base_url)
    return False


async def _fetch_openai_compatible_models(config: Config, limit: int) -> list[ModelOption]:
    base_url = (config.base_url or "").rstrip("/")
    url = f"{base_url}/models"
    headers: dict[str, str] = {}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        payload = response.json()

    data = payload.get("data", []) if isinstance(payload, dict) else []
    models: list[ModelOption] = []
    for item in data:
        model_id = _extract_model_id(item)
        if not model_id:
            continue
        note = _extract_model_note(item)
        models.append(ModelOption(model_id, "live", note))

    return sorted(models, key=lambda model: model.name)[:limit]


def _extract_model_id(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        value = item.get("id") or item.get("name")
        return str(value) if value else ""
    return ""


def _extract_model_note(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    context = item.get("context_length") or item.get("context_window")
    if context:
        return f"context {context}"
    return str(item.get("description") or item.get("owned_by") or "")[:80]


def _dedupe_models(models: list[ModelOption]) -> list[ModelOption]:
    seen: set[str] = set()
    deduped: list[ModelOption] = []
    for model in models:
        if model.name in seen:
            continue
        seen.add(model.name)
        deduped.append(model)
    return deduped


def _short_error(error: Exception) -> str:
    text = str(error).replace("\n", " ").strip()
    return text[:160] or error.__class__.__name__
