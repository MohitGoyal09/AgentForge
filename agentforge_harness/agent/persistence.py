from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from agentforge_harness.client.response import TokenUsage
from agentforge_harness.config.loader import get_data_dir

SCHEMA_VERSION = 1
_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass
class SessionSnapshot:
    session_id: str
    created_at: datetime
    updated_at: datetime
    turn_count: int
    cwd: str
    config: dict[str, Any]
    messages: list[dict[str, Any]]
    latest_usage: TokenUsage
    total_usage: TokenUsage
    active_tools: list[str]
    mcp_servers: list[str]
    active_skills: list[str]
    todos: dict[str, str]
    event_sequence: int = 0
    mode: str = "build"
    name: str = ""
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "turn_count": self.turn_count,
            "cwd": self.cwd,
            "config": self.config,
            "messages": self.messages,
            "latest_usage": self.latest_usage.__dict__,
            "total_usage": self.total_usage.__dict__,
            "active_tools": self.active_tools,
            "mcp_servers": self.mcp_servers,
            "active_skills": self.active_skills,
            "todos": self.todos,
            "event_sequence": self.event_sequence,
            "mode": self.mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionSnapshot:
        return cls(
            schema_version=data.get("schema_version", 0),
            session_id=data["session_id"],
            name=data.get("name", ""),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            turn_count=data["turn_count"],
            cwd=data.get("cwd", ""),
            config=data.get("config", {}),
            messages=data["messages"],
            latest_usage=TokenUsage(**data.get("latest_usage", {})),
            total_usage=TokenUsage(**data["total_usage"]),
            active_tools=data.get("active_tools", []),
            mcp_servers=data.get("mcp_servers", []),
            active_skills=data.get("active_skills", []),
            todos=data.get("todos", {}),
            event_sequence=data.get("event_sequence", 0),
            mode=data.get("mode", "build"),
        )


class PersistenceManager:
    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or get_data_dir()
        self.sessions_dir = self.data_dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir = self.data_dir / "checkpoints"
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self.events_dir = self.data_dir / "events"
        self.events_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.sessions_dir, 0o700)
        os.chmod(self.checkpoints_dir, 0o700)
        os.chmod(self.events_dir, 0o700)

    def _validate_id(self, value: str, label: str) -> None:
        if not value or not _SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError(f"Invalid {label}: {value}")

    def _json_path(self, directory, file_id: str, label: str):
        self._validate_id(file_id, label)
        file_path = (directory / f"{file_id}.json").resolve()
        if directory.resolve() not in file_path.parents:
            raise ValueError(f"Invalid {label}: {file_id}")
        return file_path

    def _event_path(self, session_id: str):
        self._validate_id(session_id, "session_id")
        file_path = (self.events_dir / f"{session_id}.jsonl").resolve()
        if self.events_dir.resolve() not in file_path.parents:
            raise ValueError(f"Invalid session_id: {session_id}")
        return file_path

    def _write_json_atomic(self, file_path, data: dict[str, Any]) -> None:
        fd, tmp_name = tempfile.mkstemp(
            dir=file_path.parent,
            prefix=f".{file_path.name}.",
            suffix=".tmp",
            text=True,
        )

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fp:
                json.dump(data, fp, indent=2)
                fp.write("\n")
                fp.flush()
                os.fsync(fp.fileno())
            os.replace(tmp_name, file_path)
            os.chmod(file_path, 0o600)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def save_session(self, snapshot: SessionSnapshot) -> None:
        file_path = self._json_path(self.sessions_dir, snapshot.session_id, "session_id")
        self._write_json_atomic(file_path, snapshot.to_dict())

    def load_session(self, session_id: str) -> SessionSnapshot | None:
        file_path = self._json_path(self.sessions_dir, session_id, "session_id")

        if not file_path.exists():
            return None

        with open(file_path, "r", encoding="utf-8") as fp:
            data = json.load(fp)

        return SessionSnapshot.from_dict(data)

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions = []
        for file_path in self.sessions_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
            except (OSError, json.JSONDecodeError, KeyError):
                continue

            sessions.append(
                {
                    "session_id": data["session_id"],
                    "name": data.get("name", ""),
                    "created_at": data["created_at"],
                    "updated_at": data["updated_at"],
                    "turn_count": data["turn_count"],
                    "cwd": data.get("cwd", ""),
                    "mode": data.get("mode", "build"),
                }
            )

        sessions.sort(key=lambda x: x["updated_at"], reverse=True)
        return sessions

    def save_checkpoint(self, snapshot: SessionSnapshot) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        checkpoint_id = f"{snapshot.session_id}_{timestamp}"
        file_path = self._json_path(self.checkpoints_dir, checkpoint_id, "checkpoint_id")

        self._write_json_atomic(file_path, snapshot.to_dict())
        return checkpoint_id

    def load_checkpoint(self, checkpoint_id: str) -> SessionSnapshot | None:
        file_path = self._json_path(self.checkpoints_dir, checkpoint_id, "checkpoint_id")

        if not file_path.exists():
            return None

        with open(file_path, "r", encoding="utf-8") as fp:
            data = json.load(fp)

        return SessionSnapshot.from_dict(data)

    def list_checkpoints(self) -> list[dict[str, Any]]:
        checkpoints = []
        for file_path in self.checkpoints_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
            except (OSError, json.JSONDecodeError, KeyError):
                continue

            checkpoints.append(
                {
                    "checkpoint_id": file_path.stem,
                    "session_id": data["session_id"],
                    "created_at": data["created_at"],
                    "updated_at": data["updated_at"],
                    "turn_count": data["turn_count"],
                    "cwd": data.get("cwd", ""),
                    "mode": data.get("mode", "build"),
                }
            )

        checkpoints.sort(key=lambda x: x["checkpoint_id"], reverse=True)
        return checkpoints

    def append_event(
        self,
        session_id: str,
        turn: int,
        sequence: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        file_path = self._event_path(session_id)
        event = {
            "schema_version": SCHEMA_VERSION,
            "session_id": session_id,
            "turn": turn,
            "sequence": sequence,
            "type": event_type,
            "timestamp": datetime.now().isoformat(),
            "payload": payload,
        }

        file_exists = file_path.exists()
        with open(file_path, "a", encoding="utf-8") as fp:
            fp.write(json.dumps(event, default=str))
            fp.write("\n")
            fp.flush()
            os.fsync(fp.fileno())

        if not file_exists:
            os.chmod(file_path, 0o600)

    def list_events(self, session_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        file_path = self._event_path(session_id)
        if not file_path.exists():
            return []

        events: list[dict[str, Any]] = []
        with open(file_path, "r", encoding="utf-8") as fp:
            for line in fp:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        if limit is not None and limit >= 0:
            return events[-limit:]
        return events
