from __future__ import annotations

from agentforge_harness.agent.events import AgentEvent, AgentEventType
from agentforge_harness.ui.state import TuiState


class TuiEventAdapter:
    """Maps AgentEvent instances onto TuiState mutations."""

    def __init__(self, state: TuiState) -> None:
        self._state = state

    def apply(self, event: AgentEvent) -> None:
        state = self._state
        d = event.data
        t = event.type

        if t == AgentEventType.AGENT_START:
            state.running = True

        elif t == AgentEventType.AGENT_END:
            state.running = False
            state.finalize_assistant()
            state.finalize_thinking()

        elif t == AgentEventType.TEXT_DELTA:
            state.flush_assistant_delta(d.get("content", ""))

        elif t == AgentEventType.TEXT_COMPLETE:
            state.finalize_assistant()

        elif t == AgentEventType.THINKING_DELTA:
            state.flush_thinking_delta(d.get("content", ""))

        elif t == AgentEventType.TOOL_CALL_START:
            state.add_tool_item(
                call_id=d.get("call_id", ""),
                name=d.get("name", "unknown"),
                args=d.get("arguments", {}),
            )

        elif t == AgentEventType.TOOL_CALL_COMPLETE:
            state.update_tool_result(
                call_id=d.get("call_id", ""),
                output=str(d.get("output", "")),
                success=bool(d.get("success", False)),
            )

        elif t == AgentEventType.AGENT_ERROR:
            state.running = False
            state.add_error(d.get("error", "Unknown error"))
