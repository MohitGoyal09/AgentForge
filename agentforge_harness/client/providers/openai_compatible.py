from __future__ import annotations

from typing import Any, AsyncGenerator

from openai import APIConnectionError, AsyncOpenAI, APIError, RateLimitError

from agentforge_harness.config.config import Config
from agentforge_harness.client.providers.base import BaseProvider
from agentforge_harness.client.thinking import openai_reasoning_effort
from agentforge_harness.client.response import (
    StreamEvent,
    StreamEventType,
    TextDelta,
    TokenUsage,
    ToolCall,
    ToolCallDelta,
    parse_tool_call_arguments,
)


class OpenAICompatibleProvider(BaseProvider):
    """Provider for OpenAI and any OpenAI-compatible endpoint (OpenRouter, custom)."""

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._client: AsyncOpenAI | None = None

    def retryable_exceptions(self) -> tuple[type[Exception], ...]:
        return (RateLimitError, APIConnectionError, APIError)

    def _format_error(self, exc: Exception) -> str:
        if isinstance(exc, RateLimitError):
            return f"Rate limit exceeded: {getattr(exc, 'message', exc)}"
        if isinstance(exc, APIConnectionError):
            return f"API connection error: {getattr(exc, 'message', exc)}"
        if isinstance(exc, APIError):
            return f"API error: {getattr(exc, 'message', exc)}"
        return super()._format_error(exc)

    def get_client(self) -> AsyncOpenAI:
        if self._client is None:
            kwargs: dict[str, Any] = {"api_key": self.config.api_key}
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    def _build_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                },
            }
            for tool in tools
        ]

    def _cached_tokens(self, usage: Any) -> int:
        details = getattr(usage, "prompt_tokens_details", None)
        return getattr(details, "cached_tokens", 0) or 0

    async def _generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        stream: bool,
        model: str | None,
    ) -> AsyncGenerator[StreamEvent, None]:
        client = self.get_client()
        model_name = model or self.config.model_name
        kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": stream,
            "temperature": self.config.temperature,
            "max_tokens": self.config.model.max_output_tokens,
        }
        if stream:
            kwargs["stream_options"] = {"include_usage": True}
        if tools:
            kwargs["tools"] = self._build_tools(tools)
            kwargs["tool_choice"] = "auto"

        effort = openai_reasoning_effort(self.config.thinking_level)
        if effort is not None:
            kwargs["reasoning_effort"] = effort

        if stream:
            async for event in self._stream_response(client, kwargs):
                yield event
        else:
            async for event in self._non_stream_response(client, kwargs):
                yield event

    async def _stream_response(
        self, client: AsyncOpenAI, kwargs: dict[str, Any]
    ) -> AsyncGenerator[StreamEvent, None]:
        response = await client.chat.completions.create(**kwargs)

        usage: TokenUsage | None = None
        finish_reason: str | None = None
        tool_calls: dict[int, dict[str, Any]] = {}

        async for chunk in response:
            if hasattr(chunk, "usage") and chunk.usage:
                usage = TokenUsage(
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens,
                    cached_tokens=self._cached_tokens(chunk.usage),
                )

            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            if choice.finish_reason:
                finish_reason = choice.finish_reason

            if delta.content:
                yield StreamEvent(
                    type=StreamEventType.TEXT_DELTA,
                    text_delta=TextDelta(content=delta.content),
                )

            if delta.tool_calls:
                for tool_call_delta in delta.tool_calls:
                    idx = tool_call_delta.index

                    if idx not in tool_calls:
                        tool_calls[idx] = {"id": tool_call_delta.id or "", "name": "", "arguments": ""}

                    if tool_call_delta.function:
                        if tool_call_delta.function.name:
                            tool_calls[idx]["name"] = tool_call_delta.function.name
                            yield StreamEvent(
                                type=StreamEventType.TOOL_CALL_START,
                                tool_call_delta=ToolCallDelta(
                                    call_id=tool_calls[idx]["id"],
                                    name=tool_call_delta.function.name,
                                ),
                            )
                        if tool_call_delta.function.arguments:
                            tool_calls[idx]["arguments"] += tool_call_delta.function.arguments
                            yield StreamEvent(
                                type=StreamEventType.TOOL_CALL_DELTA,
                                tool_call_delta=ToolCallDelta(
                                    call_id=tool_calls[idx]["id"],
                                    name=tool_call_delta.function.name,
                                    arguments_delta=tool_call_delta.function.arguments,
                                ),
                            )

        for idx, tc in tool_calls.items():
            yield StreamEvent(
                type=StreamEventType.TOOL_CALL_COMPLETE,
                tool_call=ToolCall(
                    call_id=tc["id"],
                    name=tc["name"],
                    arguments=parse_tool_call_arguments(tc["arguments"]),
                ),
            )

        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            finish_reason=finish_reason,
            token_usage=usage,
        )

    async def _non_stream_response(
        self, client: AsyncOpenAI, kwargs: dict[str, Any]
    ) -> AsyncGenerator[StreamEvent, None]:
        response = await client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        text_delta = None
        if message.content:
            text_delta = TextDelta(content=message.content)
            yield StreamEvent(type=StreamEventType.TEXT_DELTA, text_delta=text_delta)

        if message.tool_calls:
            for tc in message.tool_calls:
                tool_call = ToolCall(
                    call_id=tc.id,
                    name=tc.function.name,
                    arguments=parse_tool_call_arguments(tc.function.arguments),
                )
                yield StreamEvent(
                    type=StreamEventType.TOOL_CALL_COMPLETE,
                    tool_call=tool_call,
                )

        usage = None
        if response.usage:
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
                cached_tokens=self._cached_tokens(response.usage),
            )

        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            text_delta=text_delta,
            finish_reason=choice.finish_reason,
            token_usage=usage,
        )
