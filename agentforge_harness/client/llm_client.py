import random
from typing import Any, AsyncGenerator
from openai import APIConnectionError, AsyncOpenAI , RateLimitError , APIError

from agentforge_harness.config.config import Config, ModelProvider
from .response import TextDelta, StreamEventType, StreamEvent, TokenUsage, ToolCall, ToolCallDelta, parse_tool_call_arguments
import asyncio
from dotenv import load_dotenv

load_dotenv()

class LLMClient:
    def __init__(self , config : Config) -> None:
        self._client : AsyncOpenAI | None = None
        self._anthropic_client: Any | None = None
        self._max_retries : int = 3
        self.config = config

    def get_client(self) -> AsyncOpenAI:
        if self._client is None:
            kwargs: dict[str, Any] = {"api_key": self.config.api_key}
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    def get_anthropic_client(self) -> Any:
        if self._anthropic_client is None:
            try:
                from anthropic import AsyncAnthropic
            except ImportError as e:
                raise RuntimeError(
                    "Anthropic provider requires the 'anthropic' package. "
                    "Install AgentForge with current package dependencies."
                ) from e

            kwargs: dict[str, Any] = {"api_key": self.config.api_key}
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._anthropic_client = AsyncAnthropic(**kwargs)
        return self._anthropic_client
    
    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
        if self._anthropic_client:
            await self._anthropic_client.close()
            self._anthropic_client = None
    
    
    def _build_tools(self , tools: list[dict[str , Any]]):
        return [
            {
                'type' : 'function' , 
                'function' : {
                    'name' : tool['name'],
                    'description' : tool.get('description', ""),
                    'parameters' : tool.get('parameters' , {'type': 'object' , 'properties' : {}})
                }
            }
            for tool in tools
        ]

    def _cached_tokens(self, usage: Any) -> int:
        details = getattr(usage, "prompt_tokens_details", None)
        return getattr(details, "cached_tokens", 0) or 0

    async def chat_completion(
        self, 
        messages: list[dict[str, Any]], 
        tools: list[dict[str, Any ]] | None = None,
        stream: bool = True,
        model: str | None = None,
        max_retries: int | None = None,
        ) -> AsyncGenerator[StreamEvent, None]:
        if self.config.provider == ModelProvider.ANTHROPIC:
            async for event in self._anthropic_chat_completion(
                messages=messages,
                tools=tools,
                model=model,
                max_retries=max_retries,
            ):
                yield event
            return

        client = self.get_client()

        model_name = model or self.config.model_name
        kwargs = {
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
            kwargs['tool_choice'] = 'auto'
            


        retry_count = self._max_retries if max_retries is None else max_retries

        for attempt in range(retry_count + 1):
            try:
                if stream:
                    async for event in self._stream_response(client, kwargs):
                        yield event
                else:
                    async for event in self._non_stream_response(client, kwargs):
                        yield event
                return

            except RateLimitError as e:
                
                if attempt < retry_count:
                    wait_time = 2 ** attempt + random.uniform(0, 1)
                    await asyncio.sleep(wait_time)
                   
                else:
                    yield StreamEvent(type=StreamEventType.ERROR, 
                    error=f"Rate limit exceeded: {e.message}")

                    return

            except APIConnectionError as e:
                if attempt < retry_count:
                    wait_time = 2 ** attempt + random.uniform(0, 1)
                    await asyncio.sleep(wait_time)

                else:
                    yield StreamEvent(type=StreamEventType.ERROR,
                    error=f"API connection error: {e.message}")

                    return
            except APIError as e:
                if attempt < retry_count:
                    wait_time = 2 ** attempt + random.uniform(0, 1)
                    await asyncio.sleep(wait_time)

                else:
                    yield StreamEvent(type=StreamEventType.ERROR,
                    error=f"API error: {e.message}")
                    return

    def _build_anthropic_tools(self, tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
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
        self,
        messages: list[dict[str, Any]],
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

    async def _anthropic_chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_retries: int | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        client = self.get_anthropic_client()
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

        retry_count = self._max_retries if max_retries is None else max_retries

        for attempt in range(retry_count + 1):
            try:
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
                return
            except Exception as e:
                if attempt < retry_count:
                    wait_time = 2 ** attempt + random.uniform(0, 1)
                    await asyncio.sleep(wait_time)
                else:
                    yield StreamEvent(
                        type=StreamEventType.ERROR,
                        error=f"Anthropic API error: {e}",
                    )
                    return

    async def _stream_response(self,client : AsyncOpenAI , kwargs : dict[str , Any]) -> AsyncGenerator[StreamEvent , None]:
        response = await client.chat.completions.create(**kwargs)

        usage : TokenUsage | None = None
        finish_reason : str | None = None
        tool_calls: dict[int , dict[str , Any]] = {}
        
        async for chunk in response:

            if hasattr(chunk , "usage") and chunk.usage:
                usage = TokenUsage(
                    prompt_tokens = chunk.usage.prompt_tokens,
                    completion_tokens = chunk.usage.completion_tokens,
                    total_tokens = chunk.usage.total_tokens,
                    cached_tokens = self._cached_tokens(chunk.usage),
                )
            
            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            if choice.finish_reason:
                finish_reason = choice.finish_reason
            
            if delta.content:
                yield StreamEvent(
                    type = StreamEventType.TEXT_DELTA , 
                    text_delta = TextDelta(content = delta.content))

            if delta.tool_calls:
                for tool_call_delta in delta.tool_calls:
                    idx = tool_call_delta.index

                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            'id' : tool_call_delta.id or "",
                            'name' : '',
                            'arguments' : ''
                        }
                    
                    if tool_call_delta.function:
                        if tool_call_delta.function.name:
                            tool_calls[idx]['name'] = tool_call_delta.function.name
                            yield StreamEvent(
                                type = StreamEventType.TOOL_CALL_START,
                                tool_call_delta=ToolCallDelta(
                                    call_id = tool_calls[idx]['id'],
                                    name = tool_call_delta.function.name,
                                ),
                            )
                    if tool_call_delta.function.arguments :
                        tool_calls[idx]['arguments'] += tool_call_delta.function.arguments

                        yield StreamEvent(
                            type = StreamEventType.TOOL_CALL_DELTA,
                            tool_call_delta=ToolCallDelta(
                                call_id=tool_calls[idx]["id"],
                                name = tool_call_delta.function.name,
                                arguments_delta=tool_call_delta.function.arguments,
                            )
                        )

        for idx , tc in tool_calls.items():
                yield StreamEvent(
                    type = StreamEventType.TOOL_CALL_COMPLETE,
                    tool_call = ToolCall(
                        call_id = tc['id'],
                        name = tc['name'],
                        arguments=parse_tool_call_arguments(tc["arguments"]),
                    )
                )                   
        yield StreamEvent(type = StreamEventType.MESSAGE_COMPLETE , finish_reason = finish_reason, token_usage = usage)

    async def _non_stream_response(self , client : AsyncOpenAI , kwargs : dict[str , Any]):
        
       response = await client.chat.completions.create(**kwargs)
       choice = response.choices[0]
       message = choice.message

       text_delta = None
       if message.content:
          text_delta = TextDelta(content = message.content)
          yield StreamEvent(type = StreamEventType.TEXT_DELTA , text_delta = text_delta)
       
       tool_calls: list[ToolCall] = []
       if message.tool_calls:
          for tc in message.tool_calls:
            tool_call = ToolCall(
                call_id = tc.id,
                name = tc.function.name,
                arguments=parse_tool_call_arguments(tc.function.arguments)
                )
            tool_calls.append(tool_call)
            yield StreamEvent(
                type=StreamEventType.TOOL_CALL_COMPLETE,
                tool_call=tool_call,
            )


       usage = None
       if response.usage:
          usage = TokenUsage(
            prompt_tokens = response.usage.prompt_tokens,
            completion_tokens = response.usage.completion_tokens,
            total_tokens = response.usage.total_tokens,
            cached_tokens = self._cached_tokens(response.usage),
          )
       
       yield StreamEvent(
        type = StreamEventType.MESSAGE_COMPLETE , 
        text_delta = text_delta , 
        finish_reason = choice.finish_reason, 
        token_usage = usage)
       
