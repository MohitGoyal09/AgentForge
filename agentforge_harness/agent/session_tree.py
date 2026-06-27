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
        continuation_content: str | None = None,
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
                "continuation_content": continuation_content,
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
    1. If any KIND_MESSAGE or KIND_COMPACTION entries appear *after* the last
       KIND_LEAF, the last such entry is the tip (it represents a new branch
       that was extended after rewinding).
    2. Otherwise the ``entry_id`` target of the last KIND_LEAF is the tip.
    3. The id of the last KIND_MESSAGE or KIND_COMPACTION entry when no leaf
       pointer exists.
    4. None when *entries* is empty or contains none of the above.
    """
    last_leaf_target: str | None = None
    last_leaf_pos: int = -1
    last_message_or_compaction_id: str | None = None
    last_message_or_compaction_pos: int = -1

    for i, entry in enumerate(entries):
        if entry.kind == KIND_LEAF:
            last_leaf_target = entry.payload.get("entry_id")
            last_leaf_pos = i
        elif entry.kind in (KIND_MESSAGE, KIND_COMPACTION):
            last_message_or_compaction_id = entry.id
            last_message_or_compaction_pos = i

    if last_leaf_target is not None:
        # A message/compaction that was appended after the leaf is the new tip.
        if last_message_or_compaction_pos > last_leaf_pos:
            return last_message_or_compaction_id
        return last_leaf_target
    return last_message_or_compaction_id


def reconstruct_messages(
    entries: list[SessionEntry],
    leaf_id: str | None = None,
) -> list[dict[str, Any]]:
    """Reconstruct the ordered message list for the path ending at *leaf_id*.

    If *leaf_id* is None, :func:`active_leaf_id` is called first.  Returns []
    when there is nothing to reconstruct.

    Compaction entries cause the ids listed in their ``replaces`` payload field
    to be omitted from the output; in their place a synthetic summary message
    is injected at the position of the FIRST replaced message in the path.
    The compaction entry itself emits nothing (its summary was already injected).

    Each returned dict includes an ``entry_id`` key: for a real message entry
    this is the entry's own id; for an injected summary it is the compaction
    entry's id.
    """
    if leaf_id is None:
        leaf_id = active_leaf_id(entries)

    if leaf_id is None:
        return []

    path = path_to_entry(entries, leaf_id)

    # Build a map from compaction entry id -> summary message dict, and collect
    # the set of all replaced message ids across all compactions in the path.
    replaced_ids: set[str] = set()
    # Map: first_replaced_id -> summary dict to inject there
    # We process compactions in path order; the first replaced id in the path
    # (by order of appearance in `path`) determines insertion point.
    compaction_summaries: dict[str, dict[str, Any]] = {}  # compaction_id -> summary dict

    for entry in path:
        if entry.kind == KIND_COMPACTION:
            replaces = entry.payload.get("replaces", [])
            replaced_ids.update(replaces)
            summary_text = entry.payload.get("summary", "")
            # Use the stored formatted content when available (produced by
            # ContextManager._build_continuation_content); fall back to the
            # plain prefix so that hand-crafted test entries still work.
            content = entry.payload.get("continuation_content") or (COMPACTION_PREFIX + summary_text)
            compaction_summaries[entry.id] = {
                "role": "user",
                "content": content,
                "tool_call_id": None,
                "tool_calls": [],
                "token_count": entry.payload.get("summary_tokens"),
                "entry_id": entry.id,
            }

    # Now determine insertion point for each compaction: the first message in
    # `path` whose id is in that compaction's `replaces` list.
    # We walk path in order; for each compaction, its insertion trigger is
    # the first path entry whose id is in its `replaces`.
    # Build: message_id -> list of compaction_ids that want to inject before it.
    # Compactions that are themselves replaced by a later compaction are suppressed
    # entirely — their summary is subsumed by the later one.
    inject_before: dict[str, list[str]] = {}  # message_entry_id -> [compaction_ids to inject]

    for entry in path:
        if entry.kind == KIND_COMPACTION:
            # If this compaction is itself replaced by a later compaction, skip it.
            if entry.id in replaced_ids:
                continue
            replaces_set = set(entry.payload.get("replaces", []))
            # Find first path message that is in replaces
            for path_entry in path:
                if path_entry.kind == KIND_MESSAGE and path_entry.id in replaces_set:
                    inject_before.setdefault(path_entry.id, []).append(entry.id)
                    break
            # If no replaced message is in the path (all were already replaced by earlier
            # compaction), fall back: inject at the compaction's position (handled below
            # by checking compaction_id_has_no_inject_point)

    # Collect compaction ids that have an injection point
    compactions_with_inject: set[str] = {
        cid
        for cids in inject_before.values()
        for cid in cids
    }

    result: list[dict[str, Any]] = []

    for entry in path:
        if entry.kind == KIND_MESSAGE:
            # Inject any pending compaction summaries before this message if it's the trigger
            if entry.id in inject_before:
                for cid in inject_before[entry.id]:
                    result.append(compaction_summaries[cid])
            # Skip this message if it was replaced
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
                    "entry_id": entry.id,
                }
            )
        elif entry.kind == KIND_COMPACTION:
            # A compaction that is itself replaced by a later compaction must not
            # emit anything — its summary is subsumed.
            if entry.id in replaced_ids:
                continue
            # If this compaction has no injection point (all replaced entries absent
            # from path), inject summary here as fallback.
            if entry.id not in compactions_with_inject:
                result.append(compaction_summaries[entry.id])
            # Otherwise already injected at the replaced-message position — skip.
        # All other kinds carry no chat messages — skip silently.

    return result
