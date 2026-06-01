from __future__ import annotations

from agentforge_harness.tools.base import ToolResult


def test_error_result_has_default_recovery_contract():
    result = ToolResult.error_result("Something failed")

    assert result.status == "error"
    assert result.summary == "Something failed"
    assert result.recovery_hint
    assert result.next_actions
    assert "[Recovery:" in result.to_model_output()
    assert "[Next:" in result.to_model_output()


def test_error_result_keeps_tool_specific_recovery_contract():
    result = ToolResult.error_result(
        "Something failed",
        summary="Specific summary",
        recovery_hint="Specific recovery",
        next_actions=["Specific next action"],
    )

    assert result.summary == "Specific summary"
    assert result.recovery_hint == "Specific recovery"
    assert result.next_actions == ["Specific next action"]
