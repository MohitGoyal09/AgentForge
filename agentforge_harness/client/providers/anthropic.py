from __future__ import annotations

from typing import Any, AsyncGenerator

from agentforge_harness.config.config import Config
from agentforge_harness.client.providers.base import BaseProvider
from agentforge_harness.client.response import (
    StreamEvent,
    StreamEventType,
    TextDelta,
    TokenUsage,
    ToolCall,
    ToolCallDelta,
    parse_tool_call_arguments,
)


class AnthropicProvider(BaseProvider):
    """Provider for Anthropic models using the native streaming API."""

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._client: Any | None = None

    def retryable_exceptions(self) -> tuple[type[Exception], ...]:
        try:
            from anthropic import APIConnectionError, APIError, RateLimitError
        except ImportError:
            return ()
        return (RateLimitError, APIConnectionError, APIError)

    def get_client(self) -> Any:
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
            except ImportError as exc:
                raise RuntimeError(
                    "Anthropic provider requires the 'anthropic' package. "
                    "Install AgentForge with current package dependencies."
                ) from exc

            kwargs: dict[str, Any] = {"api_key": self.config.api_key}
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client = AsyncAnthropic(**kwargs)
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    def _build_anthropic_tools(
        self, tools: list[dict[str, Any]] | None
    ) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        return [
            {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": tool.get("parameters", {"type": "object", "properties": {}}),
            }
            for tool in tools
        ]

    def _to_anthropic_messages(
        self, messages: list[dict[str, Any]]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        system_parts: list[str] = []
        converted: list[dict[str, Any]] = []

        for message in messages:
            role = message.get("role")
            content = message.get("content", "")

            if role == "system":
                if content:
                    system_parts.append(str(content))
                continue

            if role == "tool":
                converted.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": message.get("tool_call_id", ""),
                                "content": str(content),
                            }
                        ],
                    }
                )
                continue

            if role == "assistant" and message.get("tool_calls"):
                blocks: list[dict[str, Any]] = []
                if content:
                    blocks.append({"type": "text", "text": str(content)})
                for tool_call in message.get("tool_calls", []):
                    function = tool_call.get("function", {})
                    arguments = function.get("arguments") or "{}"
                    try:
                        parsed_args = parse_tool_call_arguments(arguments)
                    except TypeError:
                        parsed_args = {}
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tool_call.get("id", ""),
                            "name": function.get("name", ""),
                            "input": parsed_args,
                        }
                    )
                converted.append({"role": "assistant", "content": blocks})
                continue

            if role in {"user", "assistant"}:
                converted.append({"role": role, "content": str(content)})

        return "\n\n".join(system_parts) if system_parts else None, converted

    def _build_kwargs(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str | None,
    ) -> dict[str, Any]:
        system, anthropic_messages = self._to_anthropic_messages(messages)
        kwargs: dict[str, Any] = {
            "model": model or self.config.model_name,
            "messages": anthropic_messages,
            "max_tokens": self.config.model.max_output_tokens,
            "temperature": self.config.temperature,
        }
        if system:
            kwargs["system"] = system
        if anthropic_tools := self._build_anthropic_tools(tools):
            kwargs["tools"] = anthropic_tools
        return kwargs

    async def _generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        stream: bool,
        model: str | None,
    ) -> AsyncGenerator[StreamEvent, None]:
        client = self.get_client()
        kwargs = self._build_kwargs(messages, tools, model)

        if stream:
            async for event in self._stream_response(client, kwargs):
                yield event
        else:
            async for event in self._buffered_response(client, kwargs):
                yield event

    async def _stream_response(
        self, client: Any, kwargs: dict[str, Any]
    ) -> AsyncGenerator[StreamEvent, None]:
        tool_blocks: dict[int, dict[str, Any]] = {}
        input_tokens = 0
        output_tokens = 0
        stop_reason: str | None = None

        async with client.messages.stream(**kwargs) as stream:
            async for event in stream:
                etype = getattr(event, "type", None)

                if etype == "message_start":
                    usage = getattr(event.message, "usage", None)
                    input_tokens = getattr(usage, "input_tokens", 0) if usage else 0

                elif etype == "content_block_start":
                    block = event.content_block
                    if getattr(block, "type", None) == "tool_use":
                        tool_blocks[event.index] = {
                            "id": getattr(block, "id", ""),
                            "name": getattr(block, "name", ""),
                            "args": "",
                        }
                        yield StreamEvent(
                            type=StreamEventType.TOOL_CALL_START,
                            tool_call_delta=ToolCallDelta(
                                call_id=tool_blocks[event.index]["id"],
                                name=tool_blocks[event.index]["name"],
                            ),
                        )

                elif etype == "content_block_delta":
                    delta = event.delta
                    delta_type = getattr(delta, "type", None)
                    if delta_type == "text_delta":
                        text = getattr(delta, "text", "")
                        if text:
                            yield StreamEvent(
                                type=StreamEventType.TEXT_DELTA,
                                text_delta=TextDelta(content=text),
                            )
                    elif delta_type == "input_json_delta" and event.index in tool_blocks:
                        partial = getattr(delta, "partial_json", "") or ""
                        block = tool_blocks[event.index]
                        block["args"] += partial
                        yield StreamEvent(
                            type=StreamEventType.TOOL_CALL_DELTA,
                            tool_call_delta=ToolCallDelta(
                                call_id=block["id"],
                                name=block["name"],
                                arguments_delta=partial,
                            ),
                        )

                elif etype == "content_block_stop" and event.index in tool_blocks:
                    block = tool_blocks[event.index]
                    yield StreamEvent(
                        type=StreamEventType.TOOL_CALL_COMPLETE,
                        tool_call=ToolCall(
                            call_id=block["id"],
                            name=block["name"],
                            arguments=parse_tool_call_arguments(block["args"]),
                        ),
                    )

                elif etype == "message_delta":
                    stop_reason = getattr(event.delta, "stop_reason", None) or stop_reason
                    usage = getattr(event, "usage", None)
                    if usage:
                        output_tokens = getattr(usage, "output_tokens", output_tokens)

        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            finish_reason=stop_reason,
            token_usage=TokenUsage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
        )

    async def _buffered_response(
        self, client: Any, kwargs: dict[str, Any]
    ) -> AsyncGenerator[StreamEvent, None]:
        response = await client.messages.create(**kwargs)
        input_tokens = getattr(response.usage, "input_tokens", 0) if response.usage else 0
        output_tokens = getattr(response.usage, "output_tokens", 0) if response.usage else 0

        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text = getattr(block, "text", "")
                if text:
                    yield StreamEvent(
                        type=StreamEventType.TEXT_DELTA,
                        text_delta=TextDelta(content=text),
                    )
            elif block_type == "tool_use":
                tool_call = ToolCall(
                    call_id=getattr(block, "id", ""),
                    name=getattr(block, "name", ""),
                    arguments=getattr(block, "input", {}) or {},
                )
                yield StreamEvent(
                    type=StreamEventType.TOOL_CALL_START,
                    tool_call_delta=ToolCallDelta(
                        call_id=tool_call.call_id,
                        name=tool_call.name,
                    ),
                )
                yield StreamEvent(
                    type=StreamEventType.TOOL_CALL_COMPLETE,
                    tool_call=tool_call,
                )

        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            finish_reason=getattr(response, "stop_reason", None),
            token_usage=TokenUsage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
        )
