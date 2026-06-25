
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable
from agentforge_harness.config.config import ApprovalPolicy
from agentforge_harness.tools.base import ToolConfirmation
from agentforge_harness.utils.redaction import redact_tool_confirmation
import re

class ApprovalDecision(str , Enum):
    APPROVED = 'approved'
    REJECTED = 'rejected'
    NEEDS_CONFIRMATION = 'needs_confirmation'

@dataclass
class ApprovalContext:

    tool_name : str
    params : dict[str ,Any]
    is_mutating : bool
    affected_paths: list[Path]
    command : str | None = None
    is_dangerous : bool = False

DANGEROUS_PATTERNS = [
    # File system destruction
    r"rm\s+(-rf?|--recursive)\s+[/~]",
    r"rm\s+-rf?\s+\*",
    r"rmdir\s+[/~]",
    # Disk operations
    r"dd\s+if=",
    r"mkfs",
    r"fdisk",
    r"parted",
    # System control
    r"shutdown",
    r"reboot",
    r"halt",
    r"poweroff",
    r"init\s+[06]",
    # Permission changes on root
    r"chmod\s+(-R\s+)?777\s+[/~]",
    r"chown\s+-R\s+.*\s+[/~]",
    # Network exposure
    r"nc\s+-l",
    r"netcat\s+-l",
    # Code execution from network
    r"curl\s+.*\|\s*(bash|sh)",
    r"wget\s+.*\|\s*(bash|sh)",
    # Fork bomb
    r":\(\)\s*\{\s*:\|:&\s*\}\s*;",
]

# Patterns for safe commands (can be auto-approved)
SAFE_PATTERNS = [
    # Information commands
    r"^(ls|dir|pwd|cd|echo|cat|head|tail|less|more|wc)(\s|$)",
    r"^(find|locate|which|whereis|file|stat)(\s|$)",
    # Development tools (read-only)
    r"^git\s+(status|log|diff|show|branch|remote|tag)(\s|$)",
    r"^(npm|yarn|pnpm)\s+(list|ls|outdated)(\s|$)",
    r"^pip\s+(list|show|freeze)(\s|$)",
    r"^cargo\s+(tree|search)(\s|$)",
    # Text processing (usually safe)
    r"^(grep|awk|sed|cut|sort|uniq|tr|diff|comm)(\s|$)",
    # System info
    r"^(date|cal|uptime|whoami|id|groups|hostname|uname)(\s|$)",
    r"^(env|printenv|set)$",
    # Process info
    r"^(ps|top|htop|pgrep)(\s|$)",
]

def is_dangerous_command(command: str) -> bool:
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True

    return False


def is_safe_command(command: str) -> bool:
    for pattern in SAFE_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True

    return False

class ApprovalManager:
    def __init__(
        self,
        approval_policy : ApprovalPolicy,
        cwd : Path,
        confirmation_callback : Callable[[ToolConfirmation] , Awaitable[bool]] | None = None,
        redaction_enabled: bool = True,
    ):
     self.approval_policy = approval_policy
     self.cwd = cwd
     self.confirmation_callback = confirmation_callback
     self.redaction_enabled = redaction_enabled
    
    def _assess_command_safety(self, command : str) -> ApprovalDecision:
        if self.approval_policy == ApprovalPolicy.YOLO:
            return ApprovalDecision.APPROVED
        
        if is_dangerous_command(command):
            return ApprovalDecision.REJECTED

        if self.approval_policy == ApprovalPolicy.NEVER:
            if is_safe_command(command):
                return ApprovalDecision.APPROVED
            return ApprovalDecision.REJECTED

        if self.approval_policy in {ApprovalPolicy.AUTO, ApprovalPolicy.ON_FAILURE}:
            return ApprovalDecision.APPROVED
        
        if self.approval_policy == ApprovalPolicy.AUTO_EDIT:
            if is_safe_command(command):
                return ApprovalDecision.APPROVED
            return ApprovalDecision.NEEDS_CONFIRMATION
        if is_safe_command(command):
            return ApprovalDecision.APPROVED
        
        return ApprovalDecision.NEEDS_CONFIRMATION



    def _default_mutation_decision(self, has_paths: bool) -> ApprovalDecision:
        """Decision for a mutating op with no known-safe command basis.

        Applies the configured policy instead of silently approving. Covers
        in-workspace writes as well as path-less mutations (MCP tools, memory,
        network, subagents) that previously fell through to APPROVED.
        """
        policy = self.approval_policy
        if policy in {ApprovalPolicy.AUTO, ApprovalPolicy.ON_FAILURE}:
            return ApprovalDecision.APPROVED
        if policy == ApprovalPolicy.NEVER:
            # NEVER only auto-approves known-safe read-only commands; a mutating
            # action with no safe-command basis is rejected outright.
            return ApprovalDecision.REJECTED
        if policy == ApprovalPolicy.AUTO_EDIT:
            # Trust local edits (operations that name concrete paths), but still
            # confirm path-less mutations like MCP tools and memory writes.
            return ApprovalDecision.APPROVED if has_paths else ApprovalDecision.NEEDS_CONFIRMATION
        # ON_REQUEST (default) and any other policy: ask before mutating.
        return ApprovalDecision.NEEDS_CONFIRMATION

    async def check_approval(self, context : ApprovalContext) -> ApprovalDecision:
        # Read-only operations never require approval.
        if not context.is_mutating:
            return ApprovalDecision.APPROVED

        # YOLO approves everything.
        if self.approval_policy == ApprovalPolicy.YOLO:
            return ApprovalDecision.APPROVED

        # Command-based tools (shell): the command-safety assessment is
        # authoritative. It rejects dangerous commands, approves known-safe
        # ones, and asks for confirmation otherwise — we honour that verdict
        # directly rather than letting NEEDS_CONFIRMATION fall through.
        if context.command:
            return self._assess_command_safety(context.command)

        # A write that escapes the workspace, or any tool-flagged dangerous
        # action, always needs confirmation.
        escapes_workspace = any(
            not path.is_relative_to(self.cwd) for path in context.affected_paths
        )
        if escapes_workspace or context.is_dangerous:
            return ApprovalDecision.NEEDS_CONFIRMATION

        # In-workspace writes, or a mutating tool that exposed neither a command
        # nor any affected path (MCP tools, memory, network, subagents). Decide
        # from policy — never blanket-approve.
        return self._default_mutation_decision(has_paths=bool(context.affected_paths))
    
    def request_confirmation(self, confirmation: ToolConfirmation):
        display_confirmation = (
            redact_tool_confirmation(confirmation)
            if self.redaction_enabled
            else confirmation
        )
        if self.confirmation_callback:
            return self.confirmation_callback(display_confirmation)
        # No callback configured — default to asking via console
        try:
            from rich.console import Console
            console = Console()
            console.print(f"\n[bold yellow]⚠ Approval Required[/bold yellow]")
            console.print(f"  Tool: [bold]{display_confirmation.tool_name}[/bold]")
            console.print(f"  {display_confirmation.description}")
            if display_confirmation.affected_paths:
                for p in display_confirmation.affected_paths:
                    console.print(f"  Path: {p}")
            diff_text = display_confirmation.get_diff_text()
            if diff_text:
                console.print(diff_text)
            response = console.input("\n[bold]Approve? (y/n): [/bold]").strip().lower()
            return response in ("y", "yes")
        except Exception:
            return False
        

        





     


    
