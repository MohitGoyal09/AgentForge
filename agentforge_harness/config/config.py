from __future__ import annotations
from enum import Enum
import os
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field, model_validator

from agentforge_harness.client.thinking import ThinkingLevel

class ShellEnvironmentPolicy(BaseModel):
    ignore_default_excludes: bool = False
    exclude_patterns: list[str] = Field(
        default_factory=lambda: ["*KEY*", "*TOKEN*", "*SECRET*"]
    )
    set_vars: dict[str, str] = Field(default_factory=dict)


class ModelProvider(str, Enum):
    OPENROUTER = "openrouter"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    CUSTOM = "custom"


PROVIDER_DEFAULT_BASE_URLS: dict[ModelProvider, str | None] = {
    ModelProvider.OPENROUTER: "https://openrouter.ai/api/v1",
    ModelProvider.OPENAI: None,
    ModelProvider.ANTHROPIC: None,
    ModelProvider.CUSTOM: None,
}


PROVIDER_API_KEY_ENV: dict[ModelProvider, tuple[str, ...]] = {
    ModelProvider.OPENROUTER: ("OPENROUTER_API_KEY", "API_KEY"),
    ModelProvider.OPENAI: ("OPENAI_API_KEY", "API_KEY"),
    ModelProvider.ANTHROPIC: ("ANTHROPIC_API_KEY", "API_KEY"),
    ModelProvider.CUSTOM: ("API_KEY",),
}


PROVIDER_BASE_URL_ENV: dict[ModelProvider, tuple[str, ...]] = {
    ModelProvider.OPENROUTER: ("OPENROUTER_BASE_URL", "BASE_URL"),
    ModelProvider.OPENAI: ("OPENAI_BASE_URL", "BASE_URL"),
    ModelProvider.ANTHROPIC: ("ANTHROPIC_BASE_URL", "BASE_URL"),
    ModelProvider.CUSTOM: ("BASE_URL",),
}


class ModelConfig(BaseModel):
    provider: ModelProvider = ModelProvider.OPENROUTER
    name : str = "openrouter/free"
    temperature: float = Field(default=1, ge=0.0, le=2.0)
    context_window: int = 256_000
    max_output_tokens: int = Field(default=4096, ge=1)
    base_url: str | None = None
    fallbacks: list[str] = Field(default_factory=list, description="Fallback models tried in order when primary is circuit-broken or fails")
    thinking: ThinkingLevel = Field(default=ThinkingLevel.OFF, description="Reasoning/extended-thinking effort level")
    

class SubagentConfig(BaseModel):
    name: str = Field(..., description="Unique name for the subagent (used as subagent_<name>)")
    description: str = Field(..., description="What this subagent does")
    goal_prompt: str = Field(..., description="System prompt that defines the subagent's role and behavior")
    allowed_tools: list[str] | None = Field(None, description="Tools the subagent can use. If None, inherits from parent")
    max_turns: int = Field(20, ge=1, le=100, description="Maximum turns before the subagent auto-terminates")
    timeout_seconds: float = Field(600, ge=10, description="Maximum execution time in seconds")

class MCPServerConfig(BaseModel):
    enabled : bool = True
    startup_timeout_sec : float = 10

    #stdio transport
    command : str | None = None
    args : list[str] = Field(default_factory=list)
    env : dict[str , str] = Field(default_factory=dict)
    cwd : Path | None = None

    # http/see transport
    url : str | None = None

    @model_validator(mode='after')
    def validate_transport(self) -> MCPServerConfig:
        has_command = self.command is not None
        has_url = self.url is not None

        if not has_command and not has_url:
            raise ValueError(
                "MCP Server must have either 'command' (stdio) or 'url' (http/sse)"
            )

        if has_command and has_url:
            raise ValueError(
                "MCP Server cannot have both 'command' (stdio) and 'url' (http/sse)"
            )
        return self

class ApprovalPolicy(str , Enum):
    ON_REQUEST = "on-request"
    ON_FAILURE = "on-failure"
    AUTO = "auto"
    AUTO_EDIT = "auto-edit"
    NEVER = "never"
    YOLO = "yolo"

class HookTrigger(str, Enum):
    BEFORE_AGENT = "before_agent"
    AFTER_AGENT = "after_agent"
    BEFORE_TOOL = "before_tool"
    AFTER_TOOL = "after_tool"
    ON_ERROR = "on_error"

class HookConfig(BaseModel):
    name : str
    trigger : HookTrigger
    command : str | None = None
    script : str | None = None
    timeout_sec : float = 30
    enabled : bool = True
    fail_closed: bool = False

    @model_validator(mode="after")
    def validate_hook(self) -> HookConfig:
        if not self.command and not self.script:
            raise ValueError("Hook must either have 'command' or 'script'")
        return self

class Config(BaseModel):
    model : ModelConfig = Field(default_factory=ModelConfig)
    cwd : Path = Field(default_factory=Path.cwd)
    shell_environment : ShellEnvironmentPolicy = Field(default_factory=ShellEnvironmentPolicy)
    mcp_servers : dict[str , MCPServerConfig] = Field(default_factory=dict)
    hooks_enabled : bool = False
    hooks : list[HookConfig] = Field(default_factory=list)

    approval: ApprovalPolicy = ApprovalPolicy.ON_REQUEST
    max_turns : int = 100
    max_tool_output_tokens : int = 50_000
    output_hygiene_enabled: bool = True
    redaction_enabled: bool = True
    prompt_injection_protection_enabled: bool = True

    developer_instructions: str | None = None
    user_instructions: str | None = None

    debug: bool = False

    allowed_tools : list[str] | None = Field(None , description="If Set , only these tools will be available to the agent")
    subagents: list[SubagentConfig] = Field(default_factory=list, description="User-defined subagents")
    skills_enabled: bool = True
    skill_roots: list[Path] = Field(
        default_factory=list,
        description="Directories that contain skill folders with SKILL.md files",
    )

    @property
    def api_key(self) -> str | None:
        for env_name in PROVIDER_API_KEY_ENV[self.model.provider]:
            if value := os.environ.get(env_name):
                return value
        return None

    @property
    def base_url(self) -> str | None:
        if self.model.base_url:
            return self.model.base_url
        for env_name in PROVIDER_BASE_URL_ENV[self.model.provider]:
            if value := os.environ.get(env_name):
                return value
        return PROVIDER_DEFAULT_BASE_URLS[self.model.provider]

    @property
    def provider(self) -> ModelProvider:
        return self.model.provider

    @property
    def model_name(self) -> str:
        return self.model.name

    @model_name.setter
    def model_name(self, value: str) -> None:
        self.model.name = value

    @property
    def temperature(self) -> float:
        return self.model.temperature

    @temperature.setter
    def temperature(self, value: float) -> None:
        self.model.temperature = value

    @property
    def thinking_level(self) -> ThinkingLevel:
        return self.model.thinking

    @thinking_level.setter
    def thinking_level(self, value: ThinkingLevel) -> None:
        self.model.thinking = value

    def validate(self) -> list[str]:
        errors: list[str] = []

        if not self.api_key:
            env_names = " or ".join(PROVIDER_API_KEY_ENV[self.model.provider])
            errors.append(f"No API key found for provider '{self.model.provider.value}'. Set {env_names}")

        if self.model.provider == ModelProvider.CUSTOM and not self.base_url:
            errors.append("Custom provider requires model.base_url or BASE_URL")

        if not self.cwd.exists():
            errors.append(f"Working directory does not exist: {self.cwd}")

        model_name = self.model.name
        if not model_name:
            errors.append("Model name is required")

        if self.model.temperature < 0 or self.model.temperature > 2:
            errors.append(f"Temperature must be between 0 and 2, got {self.model.temperature}")

        if not self.cwd.is_dir():
            errors.append(f"Working directory is not a directory: {self.cwd}")

        for name, server in self.mcp_servers.items():
            if server.enabled and server.command:
                cmd_path = Path(server.command).expanduser()
                if not cmd_path.is_absolute():
                    import shutil
                    if not shutil.which(server.command):
                        errors.append(
                            f"MCP server '{name}': command '{server.command}' not found in PATH"
                        )
                elif not cmd_path.exists():
                    errors.append(
                        f"MCP server '{name}': command '{server.command}' does not exist"
                    )
            if server.enabled and server.cwd and not server.cwd.exists():
                errors.append(
                    f"MCP server '{name}': working directory '{server.cwd}' does not exist"
                )

        for root in self.skill_roots:
            if not root.exists():
                errors.append(f"Skill root does not exist: {root}")
            elif not root.is_dir():
                errors.append(f"Skill root is not a directory: {root}")

        for hook in self.hooks:
            if hook.enabled and hook.script:
                script_path = Path(hook.script).expanduser()
                if not script_path.is_absolute():
                    script_path = self.cwd / hook.script
                if not script_path.exists():
                    errors.append(f"Hook '{hook.name}': script '{hook.script}' not found")

        return errors

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
