from __future__ import annotations
import asyncio
import json
import logging
import random
from typing import AsyncGenerator, Callable
from agent.events import AgentEvent, AgentEventType
from agent.session import Session
from client.response import StreamEventType, TokenUsage, ToolCall, ToolResultMessage
from config.config import Config
from prompts.system import create_loop_breaker_prompt
from safety.circuit_breaker import CircuitBreakerRegistry
from tools.base import ToolConfirmation, ToolResult

logger = logging.getLogger(__name__)


class Agent:
    def __init__(self, config: Config, confirmation_callback: Callable[[ToolConfirmation], bool] | None = None):
        self.config = config
        self.session: Session | None = Session(self.config)
        self.session.approval_manager.confirmation_callback = confirmation_callback

    async def run(self, message: str):
        await self.session.hook_system.trigger_before_agent(message)
        yield AgentEvent.agents_start(message)
        self.session.context_manager.add_user_message(message)
        self.session.loop_detector.clear()

        final_response: str | None = None

        async for event in self._agentic_loop():
            yield event

            if event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content")
        await self.session.hook_system.trigger_after_agent(message, final_response or "")
        yield AgentEvent.agents_end(final_response)

    async def _agentic_loop(self) -> AsyncGenerator[AgentEvent, None]:
        max_turns = self.config.max_turns
        max_llm_retries = 3

        model_chain = [
            self.config.model_name,
            *(self.config.model.fallbacks or []),
        ]
        circuit_breaker = CircuitBreakerRegistry()

        try:
            for turn_num in range(max_turns):
                self.session.increment_turn()

                # check context budget and auto-compress if needed
                budget = self.session.context_manager.get_context_budget()
                if budget["warning"]:
                    if budget["total_tokens"] > 0:
                        yield AgentEvent.text_delta(
                            f"\n[Context: {budget['usage_pct']}% ({budget['total_tokens']}/{budget['context_window']} tokens)]"
                        )
                    if budget["critical"] or budget["usage_pct"] >= 80:
                        summary, usage = await self.session.context_manager.compress_old_messages(
                            self.session.chat_compactor
                        )
                        if summary and usage:
                            self.session.context_manager.set_latest_usage(usage)
                            self.session.context_manager.add_usage(usage)

                tool_schemas = self.session.tool_registry.get_schemas(mode=self.session.mode)

                # LLM call with circuit breaker + fallback chain
                response_text = ""
                tool_calls: list[ToolCall] = []
                usage: TokenUsage | None = None
                llm_success = False
                selected_model = model_chain[0]

                for model_idx, model_name in enumerate(model_chain):
                    if circuit_breaker.is_open(model_name):
                        yield AgentEvent.text_delta(
                            f"\n[Skipping {model_name} (circuit open)]"
                        )
                        continue

                    for attempt in range(max_llm_retries + 1):
                        response_text = ""
                        tool_calls = []
                        usage = None
                        saw_error = False

                        async for event in self.session.client.chat_completion(
                            self.session.context_manager.get_messages(),
                            tools=tool_schemas if tool_schemas else None,
                            model=model_name,
                        ):
                            if event.type == StreamEventType.TEXT_DELTA:
                                if event.text_delta:
                                    content = event.text_delta.content
                                    response_text += content
                                    yield AgentEvent.text_delta(content)
                            elif event.type == StreamEventType.TOOL_CALL_COMPLETE:
                                if event.tool_call:
                                    tool_calls.append(event.tool_call)
                            elif event.type == StreamEventType.ERROR:
                                circuit_breaker.record_failure(model_name)
                                if attempt < max_llm_retries and circuit_breaker.can_try(model_name):
                                    wait = 2 ** attempt + random.uniform(0, 1)
                                    err_msg = event.error or "unknown error"
                                    yield AgentEvent.text_delta(
                                        f"\n[{model_name} error: {err_msg}, retrying in {wait:.1f}s...]"
                                    )
                                    await asyncio.sleep(wait)
                                    saw_error = True
                                    break
                                elif attempt < max_llm_retries:
                                    yield AgentEvent.text_delta(
                                        f"\n[{model_name} circuit open after {circuit_breaker.failure_threshold} failures, trying fallback...]"
                                    )
                                    saw_error = True
                                    break
                                else:
                                    yield AgentEvent.text_delta(
                                        f"\n[{model_name} failed after {max_llm_retries + 1} attempts, trying fallback...]"
                                    )
                                    saw_error = True
                                    break
                            elif event.type == StreamEventType.MESSAGE_COMPLETE:
                                usage = event.token_usage

                        if saw_error:
                            continue

                        circuit_breaker.record_success(model_name)
                        llm_success = True
                        selected_model = model_name
                        break

                    if llm_success:
                        break

                if not llm_success:
                    yield AgentEvent.agents_error(
                        f"All models exhausted. Tried: {', '.join(model_chain)}. "
                        "Check API keys and network connectivity."
                    )
                    return

                if selected_model != model_chain[0]:
                    yield AgentEvent.text_delta(
                        f"\n[Failed over to {selected_model}]\n"
                    )

                self.session.context_manager.add_assistant_message(
                    response_text or None,
                    (
                        [
                            {
                                "id": tc.call_id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": json.dumps(tc.arguments),
                                },
                            }
                            for tc in tool_calls
                        ]
                        if tool_calls
                        else None
                    ),
                )

                yield AgentEvent.text_complete(response_text)
                if response_text:
                    self.session.loop_detector.record_action("response", text=response_text)

                if not tool_calls:
                    if usage:
                        self.session.context_manager.set_latest_usage(usage)
                        self.session.context_manager.add_usage(usage)

                    self.session.context_manager.prune_tool_outputs()
                    return

                tool_call_results: list[ToolResultMessage] = []

                for tool_call in tool_calls:
                    yield AgentEvent.tool_call_start(
                        tool_call.call_id,
                        tool_call.name,
                        tool_call.arguments,
                    )
                    self.session.loop_detector.record_action(
                        "tool_call",
                        tool_name=tool_call.name,
                        args=tool_call.arguments,
                    )

                    try:
                        result = await self.session.tool_registry.invoke(
                            tool_call.name,
                            tool_call.arguments,
                            self.config.cwd,
                            self.session.hook_system,
                            self.session.approval_manager,
                        )
                    except Exception as e:
                        logger.warning(
                            "Tool '%s' crashed: %s",
                            tool_call.name,
                            e,
                        )
                        yield AgentEvent.text_delta(
                            f"\n[Tool '{tool_call.name}' crashed: {e}]"
                        )
                        result = ToolResult.error_result(f"Tool crashed: {e}")

                    yield AgentEvent.tool_call_complete(
                        tool_call.call_id,
                        tool_call.name,
                        result,
                    )

                    tool_call_results.append(
                        ToolResultMessage(
                            tool_call_id=tool_call.call_id,
                            content=result.to_model_output(),
                            is_error=not result.success,
                        )
                    )

                for tool_result in tool_call_results:
                    self.session.context_manager.add_tool_result(
                        tool_result.tool_call_id,
                        tool_result.content,
                    )

                if usage:
                    self.session.context_manager.set_latest_usage(usage)
                    self.session.context_manager.add_usage(usage)

                loop_detection_error = self.session.loop_detector.check_for_loop()
                if loop_detection_error:
                    loop_prompt = create_loop_breaker_prompt(loop_detection_error)
                    self.session.context_manager.add_user_message(loop_prompt)
                    self.session.loop_detector.clear()
                    self.session.context_manager.prune_tool_outputs()
                    continue

                self.session.context_manager.prune_tool_outputs()

            yield AgentEvent.agents_error(f"Maximum turns ({max_turns}) reached")

        except Exception as e:
            logger.exception("Unhandled exception in agent loop")
            try:
                self.session.save_checkpoint(mode="crash")
            except Exception:
                logger.warning("Failed to save crash checkpoint")
            yield AgentEvent.agents_error(
                f"Internal agent error: {str(e)}",
                details={"turn": self.session._turn_count},
            )
            return

    async def __aenter__(self) -> Agent:
        await self.session.initialize()
        return self

    async def __aexit__(
        self,
        exc_type,
        exc_val,
        exc_tb,
    ) -> None:
        if self.session and self.session.client and self.session.mcp_manager:
            await self.session.client.close()
            await self.session.mcp_manager.shutdown()
            self.session = None
