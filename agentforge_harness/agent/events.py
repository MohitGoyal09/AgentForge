from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agentforge_harness.client.response import TokenUsage
from agentforge_harness.tools.base import ToolResult


class AgentEventType(str, Enum):
    # Agent lifecycle events
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    AGENT_ERROR = "agent_error"

    # Tool Calls
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_COMPLETE = "tool_call_complete"

    # Text Streaming Events
    TEXT_DELTA = "text_delta"
    TEXT_COMPLETE = "text_complete"


@dataclass
class AgentEvent:
    type: AgentEventType
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def agents_start(cls, message: str) -> AgentEvent:
        return cls(
            type=AgentEventType.AGENT_START,
            data={"message": message},
        )

    @classmethod
    def agents_end(
        cls, response: str | None = None, usage: TokenUsage | None = None
    ) -> AgentEvent:
        return cls(
            type=AgentEventType.AGENT_END,
            data={
                "response": response,
                "usage": usage.__dict__ if usage else None,
            },
        )

    @classmethod
    def agents_error(
        cls, error: str, details: dict[str, Any] | None = None
    ) -> AgentEvent:
        return cls(
            type=AgentEventType.AGENT_ERROR,
            data={
                "error": error,
                "details": details or {},
            },
        )

    @classmethod
    def text_delta(cls, content: str) -> AgentEvent:
        return cls(
            type=AgentEventType.TEXT_DELTA,
            data={"content": content},
        )

    @classmethod
    def text_complete(cls, content: str) -> AgentEvent:
        return cls(
            type=AgentEventType.TEXT_COMPLETE,
            data={"content": content},
        )

    @classmethod
    def tool_call_start(
        cls, call_id: str, name: str, arguments: dict[str, Any]
    ) -> AgentEvent:
        return cls(
            type=AgentEventType.TOOL_CALL_START,
            data={
                "call_id": call_id,
                "name": name,
                "arguments": arguments,
            },
        )

    @classmethod
    def tool_call_complete(
        cls, call_id: str, name: str, result: ToolResult
    ) -> AgentEvent:
        return cls(
            type=AgentEventType.TOOL_CALL_COMPLETE,
            data={
                "call_id": call_id,
                "name": name,
                "success": result.success,
                "output": result.output,
                "error": result.error,
                "metadata": result.metadata,
                "diff": result.diff_text,
                "truncated": result.truncated,
                "exit_code" : result.exit_code,
            },
        )
