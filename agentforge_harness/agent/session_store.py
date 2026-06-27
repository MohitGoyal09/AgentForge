from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from agentforge_harness.agent.session_tree import (
    SessionEntry,
    reconstruct_messages,
)
from agentforge_harness.config.loader import get_data_dir

_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


class SessionTreeStore:
    """Append-only JSONL persistence for session history trees."""

    def __init__(self, data_dir: Path | None = None) -> None:
        base = data_dir or get_data_dir()
        self._dir = base / "session_trees"
        self._dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self._dir, 0o700)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_session_id(self, session_id: str) -> None:
        if not session_id or not _SAFE_ID_PATTERN.fullmatch(session_id):
            raise ValueError(f"Invalid session_id: {session_id!r}")

    def _path(self, session_id: str) -> Path:
        """Return the resolved JSONL path for *session_id*, rejecting traversal."""
        self._validate_session_id(session_id)
        file_path = (self._dir / f"{session_id}.jsonl").resolve()
        if self._dir.resolve() not in file_path.parents:
            raise ValueError(f"Invalid session_id (path traversal): {session_id!r}")
        return file_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def exists(self, session_id: str) -> bool:
        """Return True if a JSONL file exists for *session_id*."""
        return self._path(session_id).exists()

    def append(self, session_id: str, entry: SessionEntry) -> None:
        """Append a single *entry* to the JSONL file for *session_id*.

        Creates the file on first write and sets mode 0o600.
        """
        file_path = self._path(session_id)
        file_exists = file_path.exists()

        with open(file_path, "a", encoding="utf-8") as fp:
            fp.write(json.dumps(entry.to_dict(), default=str))
            fp.write("\n")
            fp.flush()
            os.fsync(fp.fileno())

        if not file_exists:
            os.chmod(file_path, 0o600)

    def append_many(self, session_id: str, entries: list[SessionEntry]) -> None:
        """Append multiple entries in a single open/close cycle."""
        if not entries:
            return

        file_path = self._path(session_id)
        file_exists = file_path.exists()

        with open(file_path, "a", encoding="utf-8") as fp:
            for entry in entries:
                fp.write(json.dumps(entry.to_dict(), default=str))
                fp.write("\n")
            fp.flush()
            os.fsync(fp.fileno())

        if not file_exists:
            os.chmod(file_path, 0o600)

    def read_all(self, session_id: str) -> list[SessionEntry]:
        """Read all entries from the JSONL file; skip malformed lines.

        Returns [] when the file does not exist.
        """
        file_path = self._path(session_id)
        if not file_path.exists():
            return []

        entries: list[SessionEntry] = []
        with open(file_path, "r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(SessionEntry.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    continue

        return entries

    def reconstruct(
        self,
        session_id: str,
        leaf_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Convenience: read_all then reconstruct_messages."""
        entries = self.read_all(session_id)
        return reconstruct_messages(entries, leaf_id=leaf_id)

    def write_all(self, session_id: str, entries: list[SessionEntry]) -> None:
        """Atomically overwrite the JSONL file with *entries*.

        Writes to a temp file in the same directory then os.replace so that
        concurrent readers always see a complete file.  Sets mode 0o600.
        """
        file_path = self._path(session_id)
        fd, tmp_name = tempfile.mkstemp(
            dir=self._dir,
            prefix=f".{session_id}.",
            suffix=".tmp",
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fp:
                for entry in entries:
                    fp.write(json.dumps(entry.to_dict(), default=str))
                    fp.write("\n")
                fp.flush()
                os.fsync(fp.fileno())
            os.replace(tmp_name, file_path)
            os.chmod(file_path, 0o600)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def list_session_ids(self) -> list[str]:
        """Return the stems of all *.jsonl files in the store directory."""
        return [p.stem for p in sorted(self._dir.glob("*.jsonl"))]


# ---------------------------------------------------------------------------
# Migration helper
# ---------------------------------------------------------------------------


def migrate_snapshot_to_entries(
    snapshot: Any,
    *,
    timestamp: str | None = None,
) -> list[SessionEntry]:
    """Convert a SessionSnapshot (or duck-typed equivalent) to a linear chain.

    Produces:
    - One leading INFO entry (root, parent_id=None) carrying cwd/title/created_at.
    - One SessionEntry.message per message dict in *snapshot.messages*, each
      linking to the previous entry via parent_id.

    All entries share the same *timestamp* string (defaults to
    ``snapshot.updated_at.isoformat()``).  The function is pure: it never
    calls datetime.now() or uuid4 without a deterministic seed — entry ids are
    generated by the SessionEntry constructors (uuid4.hex), which is acceptable
    since the caller can always re-run migration to get new ids.

    Returns the list in order (root first).
    """
    ts: str = timestamp if timestamp is not None else snapshot.updated_at.isoformat()

    created_at_str: str = ""
    try:
        created_at_str = snapshot.created_at.isoformat()
    except AttributeError:
        created_at_str = str(getattr(snapshot, "created_at", ""))

    cwd: str = getattr(snapshot, "cwd", "")
    name: str = getattr(snapshot, "name", "")

    # Root info entry
    root = SessionEntry.info(
        parent_id=None,
        timestamp=ts,
        cwd=cwd,
        title=name,
        created_at=created_at_str,
    )

    entries: list[SessionEntry] = [root]
    prev_id: str = root.id

    messages: list[dict[str, Any]] = list(getattr(snapshot, "messages", []))

    for msg in messages:
        entry = SessionEntry.message(
            parent_id=prev_id,
            timestamp=ts,
            role=msg.get("role", ""),
            content=msg.get("content", ""),
            tool_call_id=msg.get("tool_call_id"),
            tool_calls=msg.get("tool_calls") or [],
            token_count=msg.get("token_count"),
        )
        entries.append(entry)
        prev_id = entry.id

    return entries
