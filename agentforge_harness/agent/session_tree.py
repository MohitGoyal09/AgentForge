from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

# ---------------------------------------------------------------------------
# Kind constants
# ---------------------------------------------------------------------------

KIND_MESSAGE = "message"
KIND_COMPACTION = "compaction"
KIND_LEAF = "leaf"
KIND_MODEL_CHANGE = "model_change"
KIND_THINKING_CHANGE = "thinking_change"
KIND_INFO = "info"
KIND_CUSTOM = "custom"

# Prefix prepended to the summary text when injected into the message list.
COMPACTION_PREFIX = "Summary of earlier conversation:\n"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SessionEntry:
    """One node in the append-only session history DAG."""

    id: str
    parent_id: str | None
    timestamp: str  # ISO 8601 string — caller-supplied, never generated here
    kind: str
    payload: dict[str, Any]

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "timestamp": self.timestamp,
            "kind": self.kind,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionEntry:
        return cls(
            id=data["id"],
            parent_id=data.get("parent_id"),
            timestamp=data["timestamp"],
            kind=data["kind"],
            payload=data.get("payload", {}),
        )

    # ------------------------------------------------------------------
    # Named constructors
    # ------------------------------------------------------------------

    @classmethod
    def message(
        cls,
        parent_id: str | None,
        timestamp: str,
        role: str,
        content: str,
        tool_call_id: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        token_count: int | None = None,
        entry_id: str | None = None,
    ) -> SessionEntry:
        return cls(
            id=entry_id if entry_id is not None else uuid4().hex,
            parent_id=parent_id,
            timestamp=timestamp,
            kind=KIND_MESSAGE,
            payload={
                "role": role,
                "content": content,
                "tool_call_id": tool_call_id,
                "tool_calls": tool_calls if tool_calls is not None else [],
                "token_count": token_count,
            },
        )

    @classmethod
    def compaction(
        cls,
        parent_id: str | None,
        timestamp: str,
        summary: str,
        replaces: list[str],
        summary_tokens: int | None = None,
        entry_id: str | None = None,
    ) -> SessionEntry:
        return cls(
            id=entry_id if entry_id is not None else uuid4().hex,
            parent_id=parent_id,
            timestamp=timestamp,
            kind=KIND_COMPACTION,
            payload={
                "summary": summary,
                "replaces": list(replaces),
                "summary_tokens": summary_tokens,
            },
        )

    @classmethod
    def leaf(
        cls,
        parent_id: str | None,
        timestamp: str,
        entry_id_target: str,
        entry_id: str | None = None,
    ) -> SessionEntry:
        return cls(
            id=entry_id if entry_id is not None else uuid4().hex,
            parent_id=parent_id,
            timestamp=timestamp,
            kind=KIND_LEAF,
            payload={"entry_id": entry_id_target},
        )

    @classmethod
    def model_change(
        cls,
        parent_id: str | None,
        timestamp: str,
        model: str,
        entry_id: str | None = None,
    ) -> SessionEntry:
        return cls(
            id=entry_id if entry_id is not None else uuid4().hex,
            parent_id=parent_id,
            timestamp=timestamp,
            kind=KIND_MODEL_CHANGE,
            payload={"model": model},
        )

    @classmethod
    def thinking_change(
        cls,
        parent_id: str | None,
        timestamp: str,
        level: str,
        entry_id: str | None = None,
    ) -> SessionEntry:
        return cls(
            id=entry_id if entry_id is not None else uuid4().hex,
            parent_id=parent_id,
            timestamp=timestamp,
            kind=KIND_THINKING_CHANGE,
            payload={"level": level},
        )

    @classmethod
    def info(
        cls,
        parent_id: str | None,
        timestamp: str,
        cwd: str,
        title: str = "",
        created_at: str = "",
        entry_id: str | None = None,
    ) -> SessionEntry:
        return cls(
            id=entry_id if entry_id is not None else uuid4().hex,
            parent_id=parent_id,
            timestamp=timestamp,
            kind=KIND_INFO,
            payload={"cwd": cwd, "title": title, "created_at": created_at},
        )

    @classmethod
    def custom(
        cls,
        parent_id: str | None,
        timestamp: str,
        namespace: str,
        data: dict[str, Any],
        entry_id: str | None = None,
    ) -> SessionEntry:
        return cls(
            id=entry_id if entry_id is not None else uuid4().hex,
            parent_id=parent_id,
            timestamp=timestamp,
            kind=KIND_CUSTOM,
            payload={"namespace": namespace, "data": data},
        )


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def path_to_entry(
    entries: list[SessionEntry],
    leaf_id: str,
) -> list[SessionEntry]:
    """Return the ancestor chain from the root down to *leaf_id* (inclusive).

    Raises ValueError if *leaf_id* is not found in *entries* or a cycle is
    detected.  Returns [] when *leaf_id* is None.
    """
    if leaf_id is None:  # type: ignore[comparison-overlap]
        return []

    index: dict[str, SessionEntry] = {e.id: e for e in entries}

    if leaf_id not in index:
        raise ValueError(f"Unknown leaf_id: {leaf_id!r}")

    path: list[SessionEntry] = []
    visited: set[str] = set()
    current_id: str | None = leaf_id

    while current_id is not None:
        if current_id in visited:
            raise ValueError(f"Cycle detected at entry id: {current_id!r}")
        visited.add(current_id)

        entry = index.get(current_id)
        if entry is None:
            raise ValueError(f"Unknown entry id referenced as parent: {current_id!r}")

        path.append(entry)
        current_id = entry.parent_id

    path.reverse()
    return path


def active_leaf_id(entries: list[SessionEntry]) -> str | None:
    """Return the id that represents the current active tip of the DAG.

    Resolution order:
    1. The ``entry_id`` target of the last KIND_LEAF entry in *entries*.
    2. The id of the last KIND_MESSAGE entry in *entries*.
    3. None when *entries* is empty or contains no messages/leaf pointers.
    """
    last_leaf_target: str | None = None
    last_message_id: str | None = None

    for entry in entries:
        if entry.kind == KIND_LEAF:
            last_leaf_target = entry.payload.get("entry_id")
        elif entry.kind == KIND_MESSAGE:
            last_message_id = entry.id

    if last_leaf_target is not None:
        return last_leaf_target
    return last_message_id


def reconstruct_messages(
    entries: list[SessionEntry],
    leaf_id: str | None = None,
) -> list[dict[str, Any]]:
    """Reconstruct the ordered message list for the path ending at *leaf_id*.

    If *leaf_id* is None, :func:`active_leaf_id` is called first.  Returns []
    when there is nothing to reconstruct.

    Compaction entries cause the ids listed in their ``replaces`` payload field
    to be omitted from the output; in their place a synthetic summary message
    is injected at the compaction node's position in the path.
    """
    if leaf_id is None:
        leaf_id = active_leaf_id(entries)

    if leaf_id is None:
        return []

    path = path_to_entry(entries, leaf_id)

    # Collect the set of message ids that have been superseded by a compaction.
    replaced_ids: set[str] = set()
    for entry in path:
        if entry.kind == KIND_COMPACTION:
            replaced_ids.update(entry.payload.get("replaces", []))

    result: list[dict[str, Any]] = []

    for entry in path:
        if entry.kind == KIND_MESSAGE:
            if entry.id in replaced_ids:
                continue
            p = entry.payload
            result.append(
                {
                    "role": p.get("role"),
                    "content": p.get("content"),
                    "tool_call_id": p.get("tool_call_id"),
                    "tool_calls": p.get("tool_calls", []),
                    "token_count": p.get("token_count"),
                }
            )
        elif entry.kind == KIND_COMPACTION:
            summary = entry.payload.get("summary", "")
            result.append(
                {
                    "role": "user",
                    "content": COMPACTION_PREFIX + summary,
                    "tool_call_id": None,
                    "tool_calls": [],
                    "token_count": entry.payload.get("summary_tokens"),
                }
            )
        # All other kinds (leaf, model_change, thinking_change, info, custom)
        # carry no chat messages — skip silently.

    return result
