from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar

from agentforge_harness.client.response import TokenUsage
from agentforge_harness.tools.base import ToolResult


class AgentEventType(str, Enum):
    # Agent lifecycle events
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    AGENT_ERROR = "agent_error"

    # Message lifecycle (assistant turn boundaries)
    MESSAGE_START = "message_start"
    MESSAGE_END = "message_end"

    # Tool calls
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_COMPLETE = "tool_call_complete"
    TOOL_EXECUTION_UPDATE = "tool_execution_update"

    # Text + reasoning streaming
    TEXT_DELTA = "text_delta"
    TEXT_COMPLETE = "text_complete"
    THINKING_DELTA = "thinking_delta"

    # Steering / queue state
    QUEUE_UPDATE = "queue_update"

    # Diagnostic / harness events
    RETRY = "retry"
    CIRCUIT_BREAKER = "circuit_breaker"
    COMPACTION = "compaction"
    APPROVAL_DECISION = "approval_decision"
    LOOP_DETECTED = "loop_detected"


class AgentEvent:
    """Base class for all agent-layer events.

    Each concrete event is a typed dataclass carrying its own fields, enabling
    ``isinstance`` dispatch and direct attribute access (e.g. ``event.content``).
    The ``type`` class attribute and the computed ``data`` property preserve the
    legacy envelope API so existing consumers and the persistence layer keep
    working unchanged.

    The classmethod factories return the matching typed subclass, so producers
    written against ``AgentEvent.text_delta(...)`` continue to work.
    """

    type: ClassVar[AgentEventType]

    @property
    def data(self) -> dict[str, Any]:
        return {}

    # --- lifecycle ---------------------------------------------------------- #

    @classmethod
    def agents_start(cls, message: str) -> AgentEvent:
        return AgentStartEvent(message=message)

    @classmethod
    def agents_end(cls, response: str | None = None, usage: TokenUsage | None = None) -> AgentEvent:
        return AgentEndEvent(response=response, usage=usage)

    @classmethod
    def agents_error(cls, error: str, details: dict[str, Any] | None = None) -> AgentEvent:
        return AgentErrorEvent(error=error, details=details or {})

    # --- message lifecycle -------------------------------------------------- #

    @classmethod
    def message_start(cls, role: str = "assistant") -> AgentEvent:
        return MessageStartEvent(role=role)

    @classmethod
    def message_end(cls, content: str = "", role: str = "assistant") -> AgentEvent:
        return MessageEndEvent(content=content, role=role)

    # --- text + reasoning --------------------------------------------------- #

    @classmethod
    def text_delta(cls, content: str) -> AgentEvent:
        return TextDeltaEvent(content=content)

    @classmethod
    def text_complete(cls, content: str) -> AgentEvent:
        return TextCompleteEvent(content=content)

    @classmethod
    def thinking_delta(cls, content: str) -> AgentEvent:
        return ThinkingDeltaEvent(content=content)

    # --- tools -------------------------------------------------------------- #

    @classmethod
    def tool_call_start(cls, call_id: str, name: str, arguments: dict[str, Any]) -> AgentEvent:
        return ToolCallStartEvent(call_id=call_id, name=name, arguments=arguments)

    @classmethod
    def tool_call_complete(cls, call_id: str, name: str, result: ToolResult) -> AgentEvent:
        return ToolCallCompleteEvent(call_id=call_id, name=name, result=result)

    @classmethod
    def tool_execution_update(cls, call_id: str, name: str, message: str) -> AgentEvent:
        return ToolExecutionUpdateEvent(call_id=call_id, name=name, message=message)

    # --- steering ----------------------------------------------------------- #

    @classmethod
    def queue_update(
        cls,
        steering: list[str] | None = None,
        follow_up: list[str] | None = None,
    ) -> AgentEvent:
        return QueueUpdateEvent(steering=steering or [], follow_up=follow_up or [])

    # --- diagnostic --------------------------------------------------------- #

    @classmethod
    def retry(cls, model: str, attempt: int, error: str, delay: float | None = None) -> AgentEvent:
        return RetryEvent(model=model, attempt=attempt, error=error, delay=delay)

    @classmethod
    def circuit_breaker(cls, model: str, state: str, message: str = "") -> AgentEvent:
        return CircuitBreakerEvent(model=model, state=state, message=message)

    @classmethod
    def compaction(cls, message: str = "", summary_tokens: int | None = None) -> AgentEvent:
        return CompactionEvent(message=message, summary_tokens=summary_tokens)

    @classmethod
    def approval_decision(cls, tool_name: str, decision: str) -> AgentEvent:
        return ApprovalDecisionEvent(tool_name=tool_name, decision=decision)

    @classmethod
    def loop_detected(cls, message: str) -> AgentEvent:
        return LoopDetectedEvent(message=message)


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AgentStartEvent(AgentEvent):
    type: ClassVar[AgentEventType] = AgentEventType.AGENT_START
    message: str

    @property
    def data(self) -> dict[str, Any]:
        return {"message": self.message}


@dataclass(frozen=True)
class AgentEndEvent(AgentEvent):
    type: ClassVar[AgentEventType] = AgentEventType.AGENT_END
    response: str | None = None
    usage: TokenUsage | None = None

    @property
    def data(self) -> dict[str, Any]:
        return {
            "response": self.response,
            "usage": self.usage.__dict__ if self.usage else None,
        }


@dataclass(frozen=True)
class AgentErrorEvent(AgentEvent):
    type: ClassVar[AgentEventType] = AgentEventType.AGENT_ERROR
    error: str
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def data(self) -> dict[str, Any]:
        return {"error": self.error, "details": dict(self.details)}


# --------------------------------------------------------------------------- #
# Message lifecycle
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MessageStartEvent(AgentEvent):
    type: ClassVar[AgentEventType] = AgentEventType.MESSAGE_START
    role: str = "assistant"

    @property
    def data(self) -> dict[str, Any]:
        return {"role": self.role}


@dataclass(frozen=True)
class MessageEndEvent(AgentEvent):
    type: ClassVar[AgentEventType] = AgentEventType.MESSAGE_END
    content: str = ""
    role: str = "assistant"

    @property
    def data(self) -> dict[str, Any]:
        return {"role": self.role, "content": self.content}


# --------------------------------------------------------------------------- #
# Text + reasoning
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TextDeltaEvent(AgentEvent):
    type: ClassVar[AgentEventType] = AgentEventType.TEXT_DELTA
    content: str

    @property
    def data(self) -> dict[str, Any]:
        return {"content": self.content}


@dataclass(frozen=True)
class TextCompleteEvent(AgentEvent):
    type: ClassVar[AgentEventType] = AgentEventType.TEXT_COMPLETE
    content: str

    @property
    def data(self) -> dict[str, Any]:
        return {"content": self.content}


@dataclass(frozen=True)
class ThinkingDeltaEvent(AgentEvent):
    type: ClassVar[AgentEventType] = AgentEventType.THINKING_DELTA
    content: str

    @property
    def data(self) -> dict[str, Any]:
        return {"content": self.content}


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ToolCallStartEvent(AgentEvent):
    type: ClassVar[AgentEventType] = AgentEventType.TOOL_CALL_START
    call_id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    @property
    def data(self) -> dict[str, Any]:
        return {"call_id": self.call_id, "name": self.name, "arguments": dict(self.arguments)}


@dataclass(frozen=True)
class ToolCallCompleteEvent(AgentEvent):
    type: ClassVar[AgentEventType] = AgentEventType.TOOL_CALL_COMPLETE
    call_id: str
    name: str
    result: ToolResult

    @property
    def data(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "name": self.name,
            "success": self.result.success,
            "output": self.result.output,
            "error": self.result.error,
            "metadata": self.result.metadata,
            "diff": self.result.diff_text,
            "truncated": self.result.truncated,
            "exit_code": self.result.exit_code,
        }


@dataclass(frozen=True)
class ToolExecutionUpdateEvent(AgentEvent):
    type: ClassVar[AgentEventType] = AgentEventType.TOOL_EXECUTION_UPDATE
    call_id: str
    name: str
    message: str

    @property
    def data(self) -> dict[str, Any]:
        return {"call_id": self.call_id, "name": self.name, "message": self.message}


# --------------------------------------------------------------------------- #
# Steering
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class QueueUpdateEvent(AgentEvent):
    type: ClassVar[AgentEventType] = AgentEventType.QUEUE_UPDATE
    steering: list[str] = field(default_factory=list)
    follow_up: list[str] = field(default_factory=list)

    @property
    def data(self) -> dict[str, Any]:
        return {"steering": list(self.steering), "follow_up": list(self.follow_up)}


# --------------------------------------------------------------------------- #
# Diagnostic
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RetryEvent(AgentEvent):
    type: ClassVar[AgentEventType] = AgentEventType.RETRY
    model: str
    attempt: int
    error: str
    delay: float | None = None

    @property
    def data(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "attempt": self.attempt,
            "error": self.error,
            "delay": self.delay,
        }


@dataclass(frozen=True)
class CircuitBreakerEvent(AgentEvent):
    type: ClassVar[AgentEventType] = AgentEventType.CIRCUIT_BREAKER
    model: str
    state: str
    message: str = ""

    @property
    def data(self) -> dict[str, Any]:
        return {"model": self.model, "state": self.state, "message": self.message}


@dataclass(frozen=True)
class CompactionEvent(AgentEvent):
    type: ClassVar[AgentEventType] = AgentEventType.COMPACTION
    message: str = ""
    summary_tokens: int | None = None

    @property
    def data(self) -> dict[str, Any]:
        return {"message": self.message, "summary_tokens": self.summary_tokens}


@dataclass(frozen=True)
class ApprovalDecisionEvent(AgentEvent):
    type: ClassVar[AgentEventType] = AgentEventType.APPROVAL_DECISION
    tool_name: str
    decision: str

    @property
    def data(self) -> dict[str, Any]:
        return {"tool_name": self.tool_name, "decision": self.decision}


@dataclass(frozen=True)
class LoopDetectedEvent(AgentEvent):
    type: ClassVar[AgentEventType] = AgentEventType.LOOP_DETECTED
    message: str

    @property
    def data(self) -> dict[str, Any]:
        return {"message": self.message}
