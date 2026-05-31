import random
from typing import Any, AsyncGenerator
from openai import APIConnectionError, AsyncOpenAI , RateLimitError , APIError

from agentforge_harness.config.config import Config
from .response import TextDelta, StreamEventType, StreamEvent, TokenUsage, ToolCall, ToolCallDelta, parse_tool_call_arguments
import asyncio
from dotenv import load_dotenv

load_dotenv()

class LLMClient:
    def __init__(self , config : Config) -> None:
        self._client : AsyncOpenAI | None = None
        self._max_retries : int = 3
        self.config = config

    def get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
            )
        return self._client
    
    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
    
    
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
        client = self.get_client()

        model_name = model or self.config.model_name
        kwargs = {
                    "model": model_name,
                    "messages": messages,
                    "stream": stream,
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
       
