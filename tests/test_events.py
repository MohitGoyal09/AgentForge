from __future__ import annotations

from agentforge_harness.agent.events import (
    AgentEndEvent,
    AgentErrorEvent,
    AgentEvent,
    AgentEventType,
    AgentStartEvent,
    CircuitBreakerEvent,
    CompactionEvent,
    LoopDetectedEvent,
    MessageEndEvent,
    MessageStartEvent,
    QueueUpdateEvent,
    RetryEvent,
    TextCompleteEvent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolCallCompleteEvent,
    ToolCallStartEvent,
    ToolExecutionUpdateEvent,
)
from agentforge_harness.client.response import TokenUsage
from agentforge_harness.tools.base import ToolResult


# --- factories return typed variants (producers unchanged) ------------------ #


def test_factories_return_typed_variants():
    assert isinstance(AgentEvent.agents_start("hi"), AgentStartEvent)
    assert isinstance(AgentEvent.agents_end("done"), AgentEndEvent)
    assert isinstance(AgentEvent.agents_error("boom"), AgentErrorEvent)
    assert isinstance(AgentEvent.text_delta("x"), TextDeltaEvent)
    assert isinstance(AgentEvent.text_complete("x"), TextCompleteEvent)
    assert isinstance(AgentEvent.tool_call_start("c", "read_file", {}), ToolCallStartEvent)


# --- backward-compatible .type and .data ------------------------------------ #


def test_text_delta_backward_compat():
    event = AgentEvent.text_delta("hello")
    assert event.type == AgentEventType.TEXT_DELTA
    assert event.type.value == "text_delta"
    assert event.data == {"content": "hello"}
    # typed access also works
    assert event.content == "hello"


def test_tool_call_complete_data_matches_legacy_keys():
    result = ToolResult.success_result(
        "out",
        metadata={"path": "f.py"},
        diff_text="@@ diff",
        truncated=True,
        exit_code=0,
    )
    event = AgentEvent.tool_call_complete("call-1", "shell", result)

    assert event.type == AgentEventType.TOOL_CALL_COMPLETE
    assert event.data == {
        "call_id": "call-1",
        "name": "shell",
        "success": True,
        "output": "out",
        "error": None,
        "metadata": {"path": "f.py"},
        "diff": "@@ diff",
        "truncated": True,
        "exit_code": 0,
    }
    # typed access
    assert event.result is result


def test_agents_end_serializes_usage():
    usage = TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3)
    event = AgentEvent.agents_end("resp", usage=usage)
    assert event.data["response"] == "resp"
    assert event.data["usage"]["total_tokens"] == 3

    no_usage = AgentEvent.agents_end("resp")
    assert no_usage.data["usage"] is None


def test_agents_error_details_default():
    assert AgentEvent.agents_error("boom").data == {"error": "boom", "details": {}}
    assert AgentEvent.agents_error("boom", {"turn": 3}).data["details"] == {"turn": 3}


# --- new event types --------------------------------------------------------- #


def test_new_event_types_exist_and_carry_typed_fields():
    assert isinstance(AgentEvent.message_start(), MessageStartEvent)
    assert AgentEvent.message_end("final", role="assistant").content == "final"
    assert isinstance(AgentEvent.thinking_delta("t"), ThinkingDeltaEvent)
    assert isinstance(AgentEvent.tool_execution_update("c", "shell", "running"), ToolExecutionUpdateEvent)

    queue = AgentEvent.queue_update(steering=["s1"], follow_up=["f1"])
    assert isinstance(queue, QueueUpdateEvent)
    assert queue.data == {"steering": ["s1"], "follow_up": ["f1"]}

    retry = AgentEvent.retry(model="gpt", attempt=2, error="rate", delay=1.5)
    assert isinstance(retry, RetryEvent)
    assert retry.data == {"model": "gpt", "attempt": 2, "error": "rate", "delay": 1.5}

    cb = AgentEvent.circuit_breaker(model="gpt", state="open", message="skip")
    assert isinstance(cb, CircuitBreakerEvent)
    assert cb.type == AgentEventType.CIRCUIT_BREAKER

    comp = AgentEvent.compaction("compacted", summary_tokens=120)
    assert isinstance(comp, CompactionEvent)
    assert comp.summary_tokens == 120

    loop = AgentEvent.loop_detected("repeating")
    assert isinstance(loop, LoopDetectedEvent)
    assert loop.data == {"message": "repeating"}


def test_all_event_variants_expose_enum_type():
    events = [
        AgentEvent.agents_start("m"),
        AgentEvent.agents_end(),
        AgentEvent.agents_error("e"),
        AgentEvent.message_start(),
        AgentEvent.message_end(),
        AgentEvent.text_delta("t"),
        AgentEvent.text_complete("t"),
        AgentEvent.thinking_delta("t"),
        AgentEvent.tool_call_start("c", "n", {}),
        AgentEvent.tool_execution_update("c", "n", "m"),
        AgentEvent.queue_update(),
        AgentEvent.retry("m", 1, "e"),
        AgentEvent.circuit_breaker("m", "open"),
        AgentEvent.compaction(),
        AgentEvent.approval_decision("shell", "approved"),
        AgentEvent.loop_detected("m"),
    ]
    for event in events:
        assert isinstance(event.type, AgentEventType)
        # .data round-trips to a dict for persistence
        assert isinstance(event.data, dict)
