from __future__ import annotations

from typing import Any, AsyncGenerator

from dotenv import load_dotenv

from agentforge_harness.config.config import Config
from agentforge_harness.client.providers import BaseProvider, create_provider
from agentforge_harness.client.response import StreamEvent

load_dotenv()


class LLMClient:
    """Thin facade over a provider adapter.

    Keeps a stable ``chat_completion`` / ``close`` surface for the agent,
    session, and compaction layers while delegating all provider-specific
    behaviour (streaming, retries, message conversion) to a ``BaseProvider``.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._provider: BaseProvider = create_provider(config)

    @property
    def provider(self) -> BaseProvider:
        return self._provider

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = True,
        model: str | None = None,
        max_retries: int | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        async for event in self._provider.chat_completion(
            messages=messages,
            tools=tools,
            stream=stream,
            model=model,
            max_retries=max_retries,
        ):
            yield event

    async def close(self) -> None:
        await self._provider.close()
