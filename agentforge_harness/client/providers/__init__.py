from __future__ import annotations

from agentforge_harness.config.config import Config, ModelProvider
from agentforge_harness.client.providers.base import BaseProvider
from agentforge_harness.client.providers.anthropic import AnthropicProvider
from agentforge_harness.client.providers.openai_compatible import OpenAICompatibleProvider

# Registry of provider implementations keyed by config ModelProvider.
# OpenAI, OpenRouter, and custom all speak the OpenAI-compatible protocol.
PROVIDER_REGISTRY: dict[ModelProvider, type[BaseProvider]] = {
    ModelProvider.OPENAI: OpenAICompatibleProvider,
    ModelProvider.OPENROUTER: OpenAICompatibleProvider,
    ModelProvider.CUSTOM: OpenAICompatibleProvider,
    ModelProvider.ANTHROPIC: AnthropicProvider,
}


def create_provider(config: Config) -> BaseProvider:
    """Build the provider adapter for the configured model provider."""
    provider_cls = PROVIDER_REGISTRY.get(config.provider, OpenAICompatibleProvider)
    return provider_cls(config)


__all__ = [
    "BaseProvider",
    "AnthropicProvider",
    "OpenAICompatibleProvider",
    "PROVIDER_REGISTRY",
    "create_provider",
]
