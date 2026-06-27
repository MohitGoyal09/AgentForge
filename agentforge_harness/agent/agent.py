from __future__ import annotations
import asyncio
import json
import logging
import random
from typing import AsyncGenerator, Awaitable, Callable
from agentforge_harness.agent.events import AgentEvent, AgentEventType
from agentforge_harness.agent.modes import AgentMode
from agentforge_harness.agent.session import Session
from agentforge_harness.client.response import StreamEventType, TokenUsage, ToolCall, ToolResultMessage
from agentforge_harness.config.config import Config
from agentforge_harness.prompts.system import create_loop_breaker_prompt
from agentforge_harness.tools.base import ToolConfirmation, ToolKind, ToolResult
from agentforge_harness.utils.redaction import redact_tool_params

logger = logging.getLogger(__name__)


class Agent:
    def __init__(
        self,
        config: Config,
        confirmation_callback: Callable[[ToolConfirmation], Awaitable[bool]] | None = None,
        record_events: bool = True,
    ):
        self.config = config
        self.session: Session | None = Session(self.config)
        self.session.approval_manager.confirmation_callback = confirmation_callback
        self._record_events = record_events

    def _record(self, event: AgentEvent) -> None:
        """Persist an event. Lives in the agent so embedded (non-CLI) usage is
        logged too. Never lets a persistence failure crash the run."""
        if not self._record_events or not self.session:
            return
        try:
            self.session.record_event(event.type.value, event.data)
        except Exception:
            logger.warning("Failed to record event %s", event.type, exc_info=True)

    async def run(self, message: str):
        self.session._running = True
        try:
            await self.session.hook_system.trigger_before_agent(message)
            start_event = AgentEvent.agents_start(message)
            self._record(start_event)
            yield start_event
            self.session.context_manager.add_user_message(message)
            self.session.loop_detector.clear()

            final_response: str | None = None

            async for event in self._agentic_loop():
                self._record(event)
                yield event

                if event.type == AgentEventType.TEXT_COMPLETE:
                    final_response = event.data.get("content")
            await self.session.hook_system.trigger_after_agent(message, final_response or "")
            end_event = AgentEvent.agents_end(final_response)
            self._record(end_event)
            yield end_event
        finally:
            self.session._running = False
            # Clear any cancellation so a stale flag from this run does not
            # carry over to the next run() call.
            self.session.reset_cancel()
            # Discard any unprocessed steers — prevents ghost context from
            # leaking into the next run() call after a cancel or error.
            self.session._steering_queue.clear()

    async def _agentic_loop(self) -> AsyncGenerator[AgentEvent, None]:
        max_turns = self.config.max_turns
        if self.session.mode == AgentMode.PLAN:
            max_turns = min(max_turns, 8)
        max_llm_retries = 3
        plan_tool_budget = 8
        plan_tool_calls = 0
        force_plan_response = False

        model_chain = [
            self.config.model_name,
            *(self.config.model.fallbacks or []),
        ]
        circuit_breaker = self.session.circuit_breaker

        # Repair any assistant tool_calls left without results by a prior
        # interrupted/resumed turn, so the first provider request is well-formed.
        repaired = self.session.context_manager.repair_dangling_tool_calls()
        if repaired:
            logger.info("Repaired %d dangling tool call(s) from a prior run", repaired)

        try:
            for _turn in range(max_turns):
                # Cooperative cancellation: bail before doing any work this turn.
                if self.session.cancel_requested:
                    yield AgentEvent.text_delta("\n[Cancelled]")
                    return

                self.session.increment_turn()

                # check context budget and auto-compress if needed
                budget = self.session.context_manager.get_context_budget()
                if budget["warning"]:
                    if budget["total_tokens"] > 0:
                        yield AgentEvent.text_delta(
                            f"\n[Context: {budget['usage_pct']}% ({budget['total_tokens']}/{budget['context_window']} tokens)]"
                        )
                    if budget["should_compact"]:
                        summary, usage = await self.session.context_manager.compress_old_messages(
                            self.session.chat_compactor
                        )
                        if summary and usage:
                            self.session.context_manager.set_latest_usage(usage)
                            self.session.context_manager.add_usage(usage)
                            yield AgentEvent.compaction(
                                message="Compacted older conversation history",
                                summary_tokens=usage.completion_tokens or None,
                            )
                        else:
                            # Compaction produced nothing (too few messages or it
                            # failed). Fall back to pruning old tool outputs so we
                            # do not keep growing the context silently.
                            pruned = self.session.context_manager.prune_tool_outputs()
                            if pruned:
                                yield AgentEvent.text_delta(
                                    f"\n[Context near limit: compaction unavailable, pruned {pruned} old tool result(s)]"
                                )
                            elif budget["critical"]:
                                yield AgentEvent.text_delta(
                                    "\n[Warning: context is nearly full and could not be reduced]"
                                )

                tool_schemas = (
                    []
                    if force_plan_response
                    else self.session.tool_registry.get_schemas(mode=self.session.mode)
                )

                # LLM call with circuit breaker + fallback chain
                response_text = ""
                tool_calls: list[ToolCall] = []
                usage: TokenUsage | None = None
                llm_success = False
                selected_model = model_chain[0]

                yield AgentEvent.message_start(role="assistant")

                for model_name in model_chain:
                    if circuit_breaker.is_open(model_name):
                        yield AgentEvent.circuit_breaker(
                            model=model_name,
                            state="open",
                            message=f"Skipping {model_name} (circuit open)",
                        )
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
                            max_retries=0,
                        ):
                            if event.type == StreamEventType.TEXT_DELTA:
                                if event.text_delta:
                                    content = event.text_delta.content
                                    response_text += content
                                    yield AgentEvent.text_delta(content)
                            elif event.type == StreamEventType.THINKING_DELTA:
                                if event.text_delta:
                                    yield AgentEvent.thinking_delta(event.text_delta.content)
                            elif event.type == StreamEventType.TOOL_CALL_COMPLETE:
                                if event.tool_call:
                                    tool_calls.append(event.tool_call)
                            elif event.type == StreamEventType.ERROR:
                                circuit_breaker.record_failure(model_name)
                                err_msg = event.error or "unknown error"
                                if response_text:
                                    # Partial text was already streamed to the
                                    # consumer this attempt — retrying would
                                    # re-stream those bytes. Surface the failure
                                    # directly instead of retrying or sleeping.
                                    yield AgentEvent.text_delta(
                                        f"\n[{model_name} error after partial output: {err_msg}, trying fallback...]"
                                    )
                                    saw_error = True
                                    break
                                elif attempt < max_llm_retries and circuit_breaker.can_try(model_name):
                                    wait = 2 ** attempt + random.uniform(0, 1)
                                    yield AgentEvent.retry(
                                        model=model_name,
                                        attempt=attempt + 1,
                                        error=err_msg,
                                        delay=wait,
                                    )
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

                            # Mid-stream cancellation: stop consuming the stream.
                            if self.session.cancel_requested:
                                break

                        if saw_error:
                            continue

                        # Post-stream cancellation check: abandon this turn cleanly
                        # before we execute any tools.
                        if self.session.cancel_requested:
                            yield AgentEvent.message_end(content=response_text, role="assistant")
                            yield AgentEvent.text_delta("\n[Cancelled]")
                            return

                        circuit_breaker.record_success(model_name)
                        llm_success = True
                        selected_model = model_name
                        break

                    if llm_success:
                        break

                if not llm_success:
                    # Close the assistant message frame opened above before
                    # bailing, so turn-boundary consumers never see an open frame.
                    yield AgentEvent.message_end(content="", role="assistant")
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
                yield AgentEvent.message_end(content=response_text, role="assistant")
                if response_text:
                    self.session.loop_detector.record_action("response", text=response_text)

                if not tool_calls:
                    if usage:
                        self.session.context_manager.set_latest_usage(usage)
                        self.session.context_manager.add_usage(usage)

                    self.session.context_manager.prune_tool_outputs()

                    # Follow-up drain: inject queued follow-up as a new user message
                    # and loop again rather than ending the run.
                    _follow_up = self.session.pop_latest_follow_up_message()
                    if _follow_up is not None:
                        self.session.context_manager.add_user_message(_follow_up)
                        yield AgentEvent.queue_update(steering=[], follow_up=[_follow_up])
                        continue

                    return

                tool_call_results: list[ToolResultMessage] = []

                # Read-only tool batches run concurrently (no approval prompts,
                # no writes). Everything else runs sequentially below.
                parallel_tools = self._can_parallelize_tools(tool_calls)
                if parallel_tools:
                    async for event in self._run_tools_parallel(tool_calls, tool_call_results):
                        yield event

                sequential_calls = [] if parallel_tools else tool_calls
                for tool_call in sequential_calls:
                    display_arguments = self._display_tool_arguments(tool_call.arguments)
                    yield AgentEvent.tool_call_start(
                        tool_call.call_id,
                        tool_call.name,
                        display_arguments,
                    )

                    skip_tool_reason: str | None = None
                    self.session.loop_detector.record_action(
                        "tool_call",
                        tool_name=tool_call.name,
                        args=tool_call.arguments,
                    )

                    if self.session.mode == AgentMode.PLAN:
                        plan_tool_calls += 1
                        if plan_tool_calls > plan_tool_budget:
                            skip_tool_reason = (
                                f"Plan mode read-only exploration limit reached "
                                f"({plan_tool_budget} tool call(s))."
                            )
                        elif loop_detection_error := self.session.loop_detector.check_for_loop():
                            skip_tool_reason = (
                                f"Plan mode stopped repeated tool exploration: "
                                f"{loop_detection_error}."
                            )

                    if skip_tool_reason:
                        result = ToolResult.error_result(
                            f"{skip_tool_reason} Stop calling tools and provide the plan now."
                        )
                        force_plan_response = True
                    else:
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

                    if skip_tool_reason:
                        yield AgentEvent.text_delta(
                            f"\n[{skip_tool_reason} Preparing a plan now.]"
                        )

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

                # Steer drain: inject any steering message the user queued while
                # this tool batch was running.  Injection happens here — after all
                # tool results are committed — so the transcript is coherent
                # (assistant + tool_calls + tool_results all present).
                _steer = self.session._steering_queue.pop_steer()
                if _steer is not None:
                    self.session.context_manager.add_user_message(_steer)
                    yield AgentEvent.queue_update(steering=[_steer], follow_up=[])

                if force_plan_response and self.session.mode == AgentMode.PLAN:
                    self.session.context_manager.add_user_message(
                        "SYSTEM NOTICE: Plan mode has enough context or is repeating tool exploration. "
                        "Do not call more tools. Produce the final plan now, with goal, approach, steps, "
                        "files to change, open questions, and the reminder to switch to /build for implementation."
                    )
                    self.session.loop_detector.clear()
                    self.session.context_manager.prune_tool_outputs()
                    continue

                if usage:
                    self.session.context_manager.set_latest_usage(usage)
                    self.session.context_manager.add_usage(usage)

                loop_detection_error = self.session.loop_detector.check_for_loop()
                if loop_detection_error:
                    yield AgentEvent.loop_detected(loop_detection_error)
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
            yield AgentEvent.message_end(content="", role="assistant")
            yield AgentEvent.agents_error(
                f"Internal agent error: {str(e)}",
                details={"turn": self.session._turn_count},
            )
            return

    def _can_parallelize_tools(self, tool_calls: list[ToolCall]) -> bool:
        """Only parallelize a batch of 2+ read-only tools in build mode.

        Read tools never require approval and never write, so concurrent
        execution is safe. Mutating/network tools (which may prompt for approval
        or write files) and plan mode (which has per-call budget/loop logic) stay
        sequential.
        """
        if len(tool_calls) < 2 or self.session.mode == AgentMode.PLAN:
            return False
        for tool_call in tool_calls:
            tool = self.session.tool_registry.get(tool_call.name)
            if tool is None or tool.kind != ToolKind.READ:
                return False
        return True

    async def _run_tools_parallel(
        self,
        tool_calls: list[ToolCall],
        tool_call_results: list[ToolResultMessage],
    ):
        """Execute a read-only tool batch concurrently, preserving event order.

        Emits all tool_call_start events, runs the invocations with
        asyncio.gather, then emits tool_call_complete and appends results in the
        original call order. Appends to ``tool_call_results`` in place.
        """
        for tool_call in tool_calls:
            yield AgentEvent.tool_call_start(
                tool_call.call_id,
                tool_call.name,
                self._display_tool_arguments(tool_call.arguments),
            )
            self.session.loop_detector.record_action(
                "tool_call",
                tool_name=tool_call.name,
                args=tool_call.arguments,
            )

        async def _invoke(tc: ToolCall) -> ToolResult:
            try:
                return await self.session.tool_registry.invoke(
                    tc.name,
                    tc.arguments,
                    self.config.cwd,
                    self.session.hook_system,
                    self.session.approval_manager,
                )
            except Exception as exc:
                logger.warning("Tool '%s' crashed: %s", tc.name, exc)
                return ToolResult.error_result(f"Tool crashed: {exc}")

        results = await asyncio.gather(*[_invoke(tc) for tc in tool_calls])

        for tool_call, result in zip(tool_calls, results):
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

    def _display_tool_arguments(self, arguments: dict) -> dict:
        if not self.config.redaction_enabled:
            return arguments
        redacted, _ = redact_tool_params(arguments)
        return redacted

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
