from __future__ import annotations
import abc
import json
from typing import Any
from pydantic import BaseModel, Field, ValidationError
from pathlib import Path
from dataclasses import dataclass, field

from enum import Enum

from pydantic.json_schema import model_json_schema

from config.config import Config


class ToolKind(str, Enum):
    READ = "read"
    WRITE = "write"
    SHELL = "shell"
    NETWORK = "network"
    MEMORY = "memory"
    MCP = "mcp"


class ToolInvocation(BaseModel):
    params: dict[str, Any]
    cwd: Path


@dataclass
class FileDiff:
    path: Path
    old_content: str
    new_content: str

    is_new_file: bool = False
    is_deletion: bool = False

    def to_diff(self) -> str:
        import difflib

        old_lines = self.old_content.splitlines(keepends=True)
        new_lines = self.new_content.splitlines(keepends=True)

        if old_lines and not old_lines[-1].endswith("\n"):
            old_lines[-1] = "\n"
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"

        old_name = "/dev/null" if self.is_new_file else str(self.path)
        new_name = "/dev/null" if self.is_deletion else str(self.path)

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=old_name,
            tofile=new_name,
        )

        return "".join(diff)


class ToolResult(BaseModel):
    success: bool
    output: str
    error: str | None = None
    truncated: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None
    artifacts: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    recovery_hint: str | None = None

    diff_text: str | None = None
    exit_code : int | None = None

    @classmethod
    def error_result(cls, error: str, output: str = "", **kwargs: Any):
        return cls(success=False, output=output, error=error, **kwargs)

    @classmethod
    def success_result(cls, output: str, **kwargs: Any):
        return cls(success=True, output=output, error=None, **kwargs)

    def _default_summary(self) -> str:
        if self.summary:
            return self.summary
        if self.error:
            return self.error
        if self.output:
            return self.output.splitlines()[0]
        return ""

    def to_model_output(self) -> str:
        observation = {
            "status": "success" if self.success else "error",
            "summary": self._default_summary(),
            "artifacts": self.artifacts,
            "next_actions": self.next_actions,
            "recovery_hint": self.recovery_hint,
        }

        if self.success:
            return f"{self.output}\n\n[tool_observation]\n{json.dumps(observation)}"

        return f"Error : {self.error}\n\nOutput:\n{self.output}\n\n[tool_observation]\n{json.dumps(observation)}"


class ToolConfirmation(BaseModel):
    tool_name: str
    params: dict[str, Any]
    description: str

    diff : FileDiff | None = None
    diff_text: str | None = None
    affected_paths : list[Path] = field(default_factory=list)
    command : str | None = None
    is_dangerous : bool = False


class Tool(abc.ABC):
    name: str = "base_tool"
    description: str = "Base tool description"
    kind: ToolKind = ToolKind.READ

    def __init__(self , config : Config) -> None:
        self.config = config

    @property
    def schema(self) -> dict[str, Any] | type[BaseModel]:
        raise NotImplementedError("Every tool must implement the schema method")

    @abc.abstractmethod
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        raise NotImplementedError("Every tool must implement the execute method")

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        schema = self.schema
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            try:
                schema(**params)
            except ValidationError as e:
                errors = []
                for error in e.errors():
                    field = ".".join(str(x) for x in error.get("loc", []))
                    msg = error.get("msg", "Validation error")
                    errors.append(f"Parameter '{field}:{msg}")

                return errors

            except Exception as e:
                return [str(e)]
        return []

    def is_mutating(self, params: dict[str, Any]) -> bool:
        return self.kind in {
            ToolKind.WRITE,
            ToolKind.SHELL,
            ToolKind.NETWORK,
            ToolKind.MEMORY,
        }

    async def get_confirmation(
        self, innvocation: ToolInvocation
    ) -> ToolConfirmation | None:
        if not self.is_mutating(innvocation.params):
            return None
        return ToolConfirmation(
            tool_name=self.name,
            params=innvocation.params,
            description=f"Execute {self.name}",
        )

    def to_openai_schema(self) -> dict[str, Any]:
        schema = self.schema

        if isinstance(schema, type) and issubclass(schema, BaseModel):
            json_schema = model_json_schema(schema, mode="serialization")
            return {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": json_schema.get("properties", {}),
                    "required": json_schema.get("required", []),
                },
            }
        if isinstance(schema, dict):
            result = {
                "name": self.name,
                "description": self.description,
            }

            if "parameters" in schema:
                result["parameters"] = schema["parameters"]
            else:
                result["parameters"] = schema

            return result

        raise ValueError(f"Invalide schema type for tool {self.name}: {type(schema)}")
