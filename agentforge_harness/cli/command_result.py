"""CommandResult — structured return value from a command handler.

Handlers encode all display intent here; the CLI (or future TUI) renders it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CommandResult:
    """Return type for every command handler.

    Lifecycle signals are acted on by the run-loop *before* display.
    ``data_type`` + ``data`` carry structured payloads for the renderer.

    data_type values and their ``data`` shapes:
      "help"            — None
      "config"          — dict (redacted config)
      "doctor"          — DoctorReport object
      "tools"           — list[Tool]
      "skills"          — {"skills": list, "active": list[str]}
      "mcp_servers"     — list[dict]
      "sessions"        — {"items", "page", "total_pages", "total_count"}
      "checkpoints"     — {"items", "page", "total_pages", "total_count"}
      "history"         — {"lines": list[str]}
      "stats"           — dict (key → value for display)
      "branch_choices"  — list[dict] from Session.tree_choices()
      "key_values"      — {"title", "rows", "footer"?, "border_style"?}
      "models"          — {"provider","current_model","models","live","message","page","total_pages","total_count"}
      "report"          — {"text": str, "is_json": bool}
      "todos"           — list[tuple[str, str]]
    """

    # Lifecycle signals
    handled: bool = True        # False → command not recognised by registry
    exit: bool = False          # stop the interactive run loop

    # Context mutations (caller acts on these before rendering)
    clear: bool = False         # clear the context manager
    compact: bool = False       # trigger LLM compaction (caller performs it)
    switch_mode: str | None = None  # "plan" or "build"
    retry: bool = False         # re-run the last user message

    # Simple display
    notice: str | None = None
    notice_title: str = "Status"
    error: str | None = None
    error_title: str = "Error"

    # Structured display payload
    data_type: str | None = None
    data: Any = None
