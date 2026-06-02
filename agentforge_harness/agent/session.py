from datetime import datetime
import json
import uuid
from typing import Any
from agentforge_harness.agent.modes import AgentMode
from agentforge_harness.client.llm_client import LLMClient
from agentforge_harness.config.config import Config, ModelProvider
from agentforge_harness.config.loader import get_data_dir
from agentforge_harness.context.compaction import ChatCompactor
from agentforge_harness.context.loop_detector import LoopDetector
from agentforge_harness.context.manager import ContextManager
from agentforge_harness.hooks.hook_system import HookSystem
from agentforge_harness.agent.persistence import PersistenceManager, SessionSnapshot
from agentforge_harness.safety.circuit_breaker import CircuitBreakerRegistry
from agentforge_harness.safety.approval import ApprovalManager
from agentforge_harness.tools.discovery import ToolDiscoveryManager
from agentforge_harness.skills.manager import SkillManager
from agentforge_harness.tools.mcp.mcp_manager import MCPManager
from agentforge_harness.tools.registry import create_default_registry


class Session:
    def __init__(self, config: Config, persistence: PersistenceManager | None = None):
        self.config = config
        self.client = LLMClient(config=config)
        self.tool_registry = create_default_registry(config=config)
        self.context_manager: ContextManager | None = None
        self.discovery_manager = ToolDiscoveryManager(
            self.config,
            self.tool_registry
        )
        self.mcp_manager = MCPManager(self.config)
        self.approval_manager = ApprovalManager(
            self.config.approval,
            self.config.cwd,
            redaction_enabled=self.config.redaction_enabled,
        )
        self.skills_manager = SkillManager(self.config.skill_roots)
        self.active_skills : list[str] = []
        self.chat_compactor = ChatCompactor(client=self.client)
        self.loop_detector = LoopDetector()
        self.circuit_breaker = CircuitBreakerRegistry()
        self.hook_system = HookSystem(config)
        self.persistence = persistence or PersistenceManager()
        self.session_id = str(uuid.uuid4())
        self.name: str = ""
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self._turn_count = 0
        self._event_sequence = 0
        self._memory_cache: str | None = None
        self.mode: AgentMode = AgentMode.BUILD
    
    async def initialize(self) -> None:
        await self.mcp_manager.initialize()
        self.mcp_manager.register_tools(self.tool_registry)
        self.discovery_manager.discover_all()
        self.skills_manager.discover()
        self.context_manager = ContextManager(
            config=self.config,
            user_memory=self._load_memory(),
            tools=self.tool_registry.get_tools(mode=self.mode),
            skills=self.skills_manager.list_skills(),
            active_skills=self.active_skills,
            active_skill_bodies=self.skills_manager.get_active_skill_bodies(self.active_skills),
            mode=self.mode,
        )


    def reset(self) -> None:
        self.session_id = str(uuid.uuid4())
        self.name = ""
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self._turn_count = 0
        self._event_sequence = 0
        self.active_skills = []
        self.mode = AgentMode.BUILD
        self.circuit_breaker.reset()
        if self.context_manager:
            self.context_manager.clear()
        self.loop_detector.clear()
        todo_tool = self.tool_registry.get("todos")
        if todo_tool and hasattr(todo_tool, "_todos"):
            getattr(todo_tool, "_todos").clear()

    def set_mode(self, mode: AgentMode) -> None:
        if self.mode == mode:
            return
        self.mode = mode
        self._refresh_mode()

    def set_model_name(self, model_name: str) -> None:
        self.config.model_name = model_name
        self.circuit_breaker.reset(model_name)
        if self.context_manager:
            self.context_manager.set_model_name(model_name)
            self.context_manager.refresh_system_prompt(
                tools=self.tool_registry.get_tools(mode=self.mode),
                mode=self.mode,
                skills=self.skills_manager.list_skills(),
                active_skills=self.active_skills,
                active_skill_bodies=self.skills_manager.get_active_skill_bodies(self.active_skills),
            )

    def set_provider(
        self,
        provider: ModelProvider,
        *,
        model_name: str,
        base_url: str | None = None,
    ) -> None:
        self.config.model.provider = provider
        self.config.model.name = model_name
        self.config.model.base_url = base_url
        self.client = LLMClient(config=self.config)
        self.chat_compactor.client = self.client
        self.circuit_breaker.reset()
        if self.context_manager:
            self.context_manager.config = self.config
            self.context_manager.set_model_name(model_name)
            self.context_manager.refresh_system_prompt(
                tools=self.tool_registry.get_tools(mode=self.mode),
                mode=self.mode,
                skills=self.skills_manager.list_skills(),
                active_skills=self.active_skills,
                active_skill_bodies=self.skills_manager.get_active_skill_bodies(self.active_skills),
            )

    def _refresh_mode(self) -> None:
        if not self.context_manager:
            return
        filtered_tools = self.tool_registry.get_tools(mode=self.mode)
        self.context_manager.refresh_system_prompt(
            tools=filtered_tools,
            mode=self.mode,
            skills=self.skills_manager.list_skills(),
            active_skills=self.active_skills,
            active_skill_bodies=self.skills_manager.get_active_skill_bodies(self.active_skills),
        )

    def increment_turn(self) -> int:
        self._turn_count += 1
        self.updated_at = datetime.now()

        return self._turn_count

    def create_snapshot(self, mode: str | None = None) -> SessionSnapshot:
        if not self.context_manager:
            raise RuntimeError("Session is not initialized")

        todos = {}
        todo_tool = self.tool_registry.get("todos")
        if todo_tool and hasattr(todo_tool, "_todos"):
            todos = dict(getattr(todo_tool, "_todos"))

        return SessionSnapshot(
            session_id=self.session_id,
            name=self.name,
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
            active_skills=list(self.active_skills),
            todos=todos,
            event_sequence=self._event_sequence,
            mode=mode or self.mode.value,
        )

    def restore_snapshot(self, snapshot: SessionSnapshot) -> None:
        if not self.context_manager:
            raise RuntimeError("Session is not initialized")

        self.session_id = snapshot.session_id
        self.name = snapshot.name
        self.created_at = snapshot.created_at
        self.updated_at = datetime.now()
        self._turn_count = snapshot.turn_count
        self._event_sequence = snapshot.event_sequence
        self.active_skills = list(snapshot.active_skills)
        try:
            self.mode = AgentMode(snapshot.mode)
        except ValueError:
            self.mode = AgentMode.BUILD
        self.context_manager.restore_messages(snapshot.messages)
        self.context_manager.restore_usage(snapshot.latest_usage, snapshot.total_usage)
        self.context_manager.refresh_system_prompt(
            tools=self.tool_registry.get_tools(mode=self.mode),
            mode=self.mode,
            skills=self.skills_manager.list_skills(),
            active_skills=self.active_skills,
            active_skill_bodies=self.skills_manager.get_active_skill_bodies(self.active_skills),
        )
        self.loop_detector.clear()

        todo_tool = self.tool_registry.get("todos")
        if todo_tool and hasattr(todo_tool, "_todos"):
            getattr(todo_tool, "_todos").clear()
            getattr(todo_tool, "_todos").update(snapshot.todos)

    def save_session(self, mode: str | None = None) -> None:
        self.persistence.save_session(self.create_snapshot(mode=mode))

    def save_checkpoint(self, mode: str | None = None) -> str:
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

    def list_skills(self) -> list:
        return self.skills_manager.list_skills()

    def activate_skill(self, name: str) -> str:
        if not self.skills_manager.has_skill(name):
            raise ValueError(f"Unknown skill: {name}")
        if name not in self.active_skills:
            self.active_skills.append(name)
        body = self.skills_manager.load_skill(name)
        self._refresh_skill_prompt()
        return body

    def deactivate_skill(self, name: str) -> bool:
        if name in self.active_skills:
            self.active_skills.remove(name)
            self.skills_manager.unload_skill(name)
            self._refresh_skill_prompt()
            return True
        return False

    def _refresh_skill_prompt(self) -> None:
        if not self.context_manager:
            return
        filtered_tools = self.tool_registry.get_tools(mode=self.mode)
        self.context_manager.refresh_system_prompt(
            tools=filtered_tools,
            mode=self.mode,
            skills=self.skills_manager.list_skills(),
            active_skills=self.active_skills,
            active_skill_bodies=self.skills_manager.get_active_skill_bodies(self.active_skills),
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
        if self._memory_cache is not None:
            return self._memory_cache

        data_dir = get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / "user_memory.json"

        if not path.exists():
            self._memory_cache = None
            return None

        try:
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
            entries = data.get("entries")
            if not entries:
                self._memory_cache = None
                return None

            lines = ["User preferences and notes:"]
            for key, value in entries.items():
                lines.append(f"- {key}: {value}")

            self._memory_cache = "\n".join(lines)
            return self._memory_cache
        except Exception:
            self._memory_cache = None
            return None
