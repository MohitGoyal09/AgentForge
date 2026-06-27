from __future__ import annotations

from pathlib import Path
from typing import Awaitable

import pytest

from agentforge_harness.config.config import ApprovalPolicy
from agentforge_harness.safety.approval import (
    ApprovalContext,
    ApprovalDecision,
    ApprovalManager,
)
from agentforge_harness.tools.base import ToolConfirmation


def _ctx(
    *,
    cwd: Path,
    is_mutating: bool = True,
    affected_paths: list[Path] | None = None,
    command: str | None = None,
    is_dangerous: bool = False,
) -> ApprovalContext:
    return ApprovalContext(
        tool_name="some_tool",
        params={},
        is_mutating=is_mutating,
        affected_paths=affected_paths or [],
        command=command,
        is_dangerous=is_dangerous,
    )


def _manager(policy: ApprovalPolicy, cwd: Path) -> ApprovalManager:
    return ApprovalManager(policy, cwd)


async def test_mutating_tool_with_empty_paths_is_not_auto_approved_on_request(tmp_path: Path):
    """Regression: a mutating tool (e.g. MCP/memory) with no affected_paths and
    no command must NOT be silently approved under on-request."""
    manager = _manager(ApprovalPolicy.ON_REQUEST, tmp_path)

    decision = await manager.check_approval(_ctx(cwd=tmp_path))

    assert decision == ApprovalDecision.NEEDS_CONFIRMATION


async def test_mutating_tool_with_empty_paths_rejected_under_never(tmp_path: Path):
    manager = _manager(ApprovalPolicy.NEVER, tmp_path)

    decision = await manager.check_approval(_ctx(cwd=tmp_path))

    assert decision == ApprovalDecision.REJECTED


@pytest.mark.parametrize("policy", [ApprovalPolicy.AUTO, ApprovalPolicy.ON_FAILURE])
async def test_mutating_tool_with_empty_paths_approved_under_auto(tmp_path: Path, policy):
    manager = _manager(policy, tmp_path)

    decision = await manager.check_approval(_ctx(cwd=tmp_path))

    assert decision == ApprovalDecision.APPROVED


async def test_yolo_approves_path_less_mutation(tmp_path: Path):
    manager = _manager(ApprovalPolicy.YOLO, tmp_path)

    decision = await manager.check_approval(_ctx(cwd=tmp_path))

    assert decision == ApprovalDecision.APPROVED


async def test_non_mutating_is_always_approved(tmp_path: Path):
    manager = _manager(ApprovalPolicy.ON_REQUEST, tmp_path)

    decision = await manager.check_approval(_ctx(cwd=tmp_path, is_mutating=False))

    assert decision == ApprovalDecision.APPROVED


async def test_out_of_workspace_write_needs_confirmation(tmp_path: Path):
    manager = _manager(ApprovalPolicy.AUTO_EDIT, tmp_path)
    outside = tmp_path.parent / "elsewhere" / "file.txt"

    decision = await manager.check_approval(
        _ctx(cwd=tmp_path, affected_paths=[outside])
    )

    assert decision == ApprovalDecision.NEEDS_CONFIRMATION


async def test_auto_edit_approves_in_workspace_write(tmp_path: Path):
    manager = _manager(ApprovalPolicy.AUTO_EDIT, tmp_path)
    inside = tmp_path / "src" / "file.txt"

    decision = await manager.check_approval(
        _ctx(cwd=tmp_path, affected_paths=[inside])
    )

    assert decision == ApprovalDecision.APPROVED


async def test_auto_edit_confirms_path_less_mutation(tmp_path: Path):
    manager = _manager(ApprovalPolicy.AUTO_EDIT, tmp_path)

    decision = await manager.check_approval(_ctx(cwd=tmp_path))

    assert decision == ApprovalDecision.NEEDS_CONFIRMATION


async def test_dangerous_command_is_rejected(tmp_path: Path):
    manager = _manager(ApprovalPolicy.ON_REQUEST, tmp_path)

    decision = await manager.check_approval(
        _ctx(cwd=tmp_path, command="rm -rf /")
    )

    assert decision == ApprovalDecision.REJECTED


async def test_safe_command_is_approved(tmp_path: Path):
    manager = _manager(ApprovalPolicy.ON_REQUEST, tmp_path)

    decision = await manager.check_approval(
        _ctx(cwd=tmp_path, command="git status")
    )

    assert decision == ApprovalDecision.APPROVED


async def test_unsafe_command_needs_confirmation_on_request(tmp_path: Path):
    """Regression: a non-safe, non-dangerous command must not fall through to
    APPROVED under on-request."""
    manager = _manager(ApprovalPolicy.ON_REQUEST, tmp_path)

    decision = await manager.check_approval(
        _ctx(cwd=tmp_path, command="python deploy.py")
    )

    assert decision == ApprovalDecision.NEEDS_CONFIRMATION


async def test_dangerous_flag_needs_confirmation(tmp_path: Path):
    manager = _manager(ApprovalPolicy.AUTO, tmp_path)
    inside = tmp_path / "file.txt"

    decision = await manager.check_approval(
        _ctx(cwd=tmp_path, affected_paths=[inside], is_dangerous=True)
    )

    assert decision == ApprovalDecision.NEEDS_CONFIRMATION


# ---------------------------------------------------------------------------
# BUG C — path traversal sequences must be rejected as workspace escapes
# ---------------------------------------------------------------------------


async def test_traversal_path_escaping_cwd_needs_confirmation(tmp_path: Path):
    """BUG C: a path like cwd/../sibling resolves outside cwd and must be treated
    as a workspace escape (NEEDS_CONFIRMATION) under ON_REQUEST policy."""
    manager = _manager(ApprovalPolicy.ON_REQUEST, tmp_path)
    # Construct a path that *literally* points inside cwd but traverses out when resolved
    traversal_path = tmp_path / ".." / "escaped_file.txt"

    decision = await manager.check_approval(
        _ctx(cwd=tmp_path, affected_paths=[traversal_path])
    )

    assert decision == ApprovalDecision.NEEDS_CONFIRMATION


async def test_traversal_path_is_rejected_as_out_of_workspace(tmp_path: Path):
    """A traversal that exits cwd is detected even under AUTO_EDIT."""
    manager = _manager(ApprovalPolicy.AUTO_EDIT, tmp_path)
    traversal_path = tmp_path / ".." / "escaped.txt"

    decision = await manager.check_approval(
        _ctx(cwd=tmp_path, affected_paths=[traversal_path])
    )

    # AUTO_EDIT confirms workspace-escaping writes.
    assert decision == ApprovalDecision.NEEDS_CONFIRMATION


# ---------------------------------------------------------------------------
# BUG D — async confirmation callback must be awaited (not returned as coroutine)
# ---------------------------------------------------------------------------


async def test_async_callback_is_awaited_and_result_honoured(tmp_path: Path):
    """BUG D: an async callback returning False must cause request_confirmation
    to return False, proving the coroutine was actually awaited."""

    async def refusing_callback(confirmation: ToolConfirmation) -> bool:
        return False

    manager = ApprovalManager(
        ApprovalPolicy.ON_REQUEST,
        tmp_path,
        confirmation_callback=refusing_callback,
    )
    confirmation = ToolConfirmation(
        tool_name="some_tool",
        params={},
        description="do something",
    )

    result = await manager.request_confirmation(confirmation)

    assert result is False


async def test_async_callback_returning_true_is_honoured(tmp_path: Path):
    """An async callback returning True must result in approval."""

    async def approving_callback(confirmation: ToolConfirmation) -> bool:
        return True

    manager = ApprovalManager(
        ApprovalPolicy.ON_REQUEST,
        tmp_path,
        confirmation_callback=approving_callback,
    )
    confirmation = ToolConfirmation(
        tool_name="some_tool",
        params={},
        description="do something",
    )

    result = await manager.request_confirmation(confirmation)

    assert result is True
