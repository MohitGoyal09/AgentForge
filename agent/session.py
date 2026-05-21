from datetime import datetime
import json
import uuid
from typing import Any
from client.llm_client import LLMClient
from config.config import Config
from config.loader import get_data_dir
from context.compaction import ChatCompactor
from context.loop_detector import LoopDetector
from context.manager import ContextManager
from hooks.hook_system import HookSystem
from agent.persistence import PersistenceManager, SessionSnapshot
from safety.approval import ApprovalManager
from tools.discovery import ToolDiscoveryManager
from tools.mcp.mcp_manager import MCPManager
from tools.registry import create_default_registery


class Session:
    def __init__(self, config: Config, persistence: PersistenceManager | None = None):
        self.config = config
        self.client = LLMClient(config=config)
        self.tool_registry = create_default_registery(config=config)
        self.context_manager: ContextManager | None = None
        self.discovery_manager = ToolDiscoveryManager(
            self.config,
            self.tool_registry
        )
        self.mcp_manager = MCPManager(self.config)
        self.approval_manager = ApprovalManager(self.config.approval , self.config.cwd)
        self.chat_compactor = ChatCompactor(client=self.client)
        self.loop_detector = LoopDetector()
        self.hook_system = HookSystem(config)
        self.persistence = persistence or PersistenceManager()
        self.session_id = str(uuid.uuid4())
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self._turn_count = 0
        self._event_sequence = 0
    
    async def initialize(self) -> None:
        await self.mcp_manager.initialize()
        self.mcp_manager.register_tools(self.tool_registry)
        self.discovery_manager.discover_all()
        self.context_manager = ContextManager(config=self.config, user_memory=self._load_memory(), tools=self.tool_registry.get_tools())


    def increment_turn(self) -> int:
        self._turn_count += 1
        self.updated_at = datetime.now()

        return self._turn_count

    def create_snapshot(self, mode: str = "build") -> SessionSnapshot:
        if not self.context_manager:
            raise RuntimeError("Session is not initialized")

        todos = {}
        todo_tool = self.tool_registry.get("todos")
        if todo_tool and hasattr(todo_tool, "_todos"):
            todos = dict(getattr(todo_tool, "_todos"))

        return SessionSnapshot(
            session_id=self.session_id,
            created_at=self.created_at,
            updated_at=datetime.now(),
            turn_count=self._turn_count,
            cwd=str(self.config.cwd),
            config=self._redact_config(self.config.to_dict()),
            messages=self.context_manager.snapshot_messages(),
            latest_usage=self.context_manager.get_latest_usage(),
            total_usage=self.context_manager.get_total_usage(),
            active_tools=[tool.name for tool in self.tool_registry.get_tools()],
            mcp_servers=[server["name"] for server in self.mcp_manager.get_all_servers()],
            active_skills=[],
            todos=todos,
            event_sequence=self._event_sequence,
            mode=mode,
        )

    def restore_snapshot(self, snapshot: SessionSnapshot) -> None:
        if not self.context_manager:
            raise RuntimeError("Session is not initialized")

        self.session_id = snapshot.session_id
        self.created_at = snapshot.created_at
        self.updated_at = datetime.now()
        self._turn_count = snapshot.turn_count
        self._event_sequence = snapshot.event_sequence
        self.context_manager.restore_messages(snapshot.messages)
        self.context_manager.restore_usage(snapshot.latest_usage, snapshot.total_usage)
        self.loop_detector.clear()

        todo_tool = self.tool_registry.get("todos")
        if todo_tool and hasattr(todo_tool, "_todos"):
            getattr(todo_tool, "_todos").clear()
            getattr(todo_tool, "_todos").update(snapshot.todos)

    def save_session(self, mode: str = "build") -> None:
        self.persistence.save_session(self.create_snapshot(mode=mode))

    def save_checkpoint(self, mode: str = "build") -> str:
        return self.persistence.save_checkpoint(self.create_snapshot(mode=mode))

    def record_event(self, event_type: str, payload: dict) -> None:
        self._event_sequence += 1
        self.persistence.append_event(
            session_id=self.session_id,
            turn=self._turn_count,
            sequence=self._event_sequence,
            event_type=event_type,
            payload=payload,
        )

    def _redact_config(self, value: Any) -> Any:
        secret_markers = ("key", "token", "secret", "password")
        if isinstance(value, dict):
            redacted = {}
            for key, item in value.items():
                if any(marker in key.lower() for marker in secret_markers):
                    redacted[key] = "[redacted]"
                else:
                    redacted[key] = self._redact_config(item)
            return redacted
        if isinstance(value, list):
            return [self._redact_config(item) for item in value]
        return value

    def _load_memory(self) -> str | None:
        data_dir = get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / "user_memory.json"

        if not path.exists():
            return None

        try:
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
            entries = data.get("entries")
            if not entries:
                return None

            lines = ["User preferences and notes:"]
            for key, value in entries.items():
                lines.append(f"- {key}: {value}")

            return "\n".join(lines)
        except Exception:
            return None
