import json
import uuid
from agentforge_harness.config.config import Config
from agentforge_harness.config.loader import get_data_dir
from agentforge_harness.tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field


class MemoryParams(BaseModel):
    action: str = Field(
        ..., description="Action: 'set', 'get', 'delete', 'list', 'clear'"
    )
    key: str | None = Field(
        None, description="Memory key (required for `set`, `get`, `delete`)"
    )
    value: str | None = Field(None, description="Value to store (required for `set`)")


class MemoryTool(Tool):
    name = "memory"
    description = "Store and retrieve persistent memory. Use this to remember user preferences, important context or notes."
    kind = ToolKind.MEMORY
    schema = MemoryParams

    def _load_memory(self) -> dict:
        data_dir = get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / "user_memory.json"

        if not path.exists():
            return {"entries": {}}

        try:
            content = path.read_text(encoding="utf-8")
            return json.loads(content)
        except Exception:
            return {"entries": {}}

    def _save_memory(self, memory: dict) -> None:
        data_dir = get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / "user_memory.json"

        path.write_text(json.dumps(memory, indent=2, ensure_ascii=False))

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = MemoryParams(**invocation.params)

        if params.action.lower() == "set":
            if not params.key or not params.value:
                return ToolResult.error_result(
                    "`key` and `value` are required for 'set' action",
                    summary="Missing key or value for set",
                    recovery_hint="Provide both `key` and `value` parameters, then retry.",
                )
            memory = self._load_memory()
            memory["entries"][params.key] = params.value
            self._save_memory(memory)

            return ToolResult.success_result(
                f"Set memory: {params.key}",
                summary=f"Memory set: {params.key}",
                next_actions=["Use 'get' to verify the stored value, or 'list' to see all memories."],
                artifacts=[params.key],
            )
        elif params.action.lower() == "get":
            if not params.key:
                return ToolResult.error_result(
                    "`key` required for 'get' action",
                    summary="Missing key for get",
                    recovery_hint="Provide the `key` parameter for the memory to retrieve, then retry.",
                )

            memory = self._load_memory()
            if params.key not in memory.get("entries", {}):
                return ToolResult.success_result(
                    f"Memory not found: {params.key}",
                    summary=f"Memory key not found: {params.key}",
                    next_actions=["Use 'list' to see all stored memories and find the correct key."],
                    artifacts=[params.key],
                    metadata={
                        "found": False,
                    },
                )
            return ToolResult.success_result(
                f"Memory found: {params.key}: {memory['entries'][params.key]}",
                summary=f"Memory retrieved: {params.key}",
                next_actions=["Use 'get' on other keys or 'set' to store new information."],
                artifacts=[params.key],
                metadata={
                    "found": True,
                },
            )
        elif params.action == "delete":
            if not params.key:
                return ToolResult.error_result(
                    "`key` required for 'delete' action",
                    summary="Missing key for delete",
                    recovery_hint="Provide the `key` parameter for the memory to delete, then retry.",
                )
            memory = self._load_memory()
            if params.key not in memory.get("entries", {}):
                return ToolResult.success_result(
                    f"Memory not found: {params.key}",
                    summary=f"Nothing to delete: {params.key} not found",
                )

            del memory["entries"][params.key]
            self._save_memory(memory)

            return ToolResult.success_result(
                f"Deleted memory: {params.key}",
                summary=f"Memory deleted: {params.key}",
                next_actions=["Use 'list' to verify deletion, or 'set' to store new information."],
                artifacts=[params.key],
            )
        elif params.action == "list":
            memory = self._load_memory()
            entries = memory.get("entries", {})
            if not entries:
                return ToolResult.success_result(
                    f"No memories stored",
                    summary="No stored memories",
                    metadata={
                        "found": False,
                    },
                )
            lines = [f"Stored memories:"]
            for key, value in sorted(entries.items()):
                lines.append(f"  {key}: {value}")

            return ToolResult.success_result(
                "\n".join(lines),
                summary=f"{len(entries)} stored memory/memories",
                next_actions=["Use 'get' to read a specific memory, or 'delete' to remove one."],
                metadata={
                    "found": True,
                },
            )
        elif params.action == "clear":
            memory = self._load_memory()
            count = len(memory.get("entries", {}))
            memory["entries"] = {}
            self._save_memory(memory)
            return ToolResult.success_result(
                f"Cleared {count} memory entries",
                summary=f"Cleared {count} memory entries",
                next_actions=["Use 'set' to store new memories as needed."],
            )
        else:
            return ToolResult.error_result(
                f"Unknown action: {params.action}",
                summary=f"Unknown action: {params.action}",
                recovery_hint="Valid actions: set, get, delete, list, clear.",
            )