from pathlib import Path
from typing import Any
from agentforge_harness.agent.modes import AgentMode
from agentforge_harness.config.config import Config
from agentforge_harness.hooks.hook_system import HookSystem
from agentforge_harness.safety.approval import ApprovalContext, ApprovalDecision, ApprovalManager
from agentforge_harness.safety.output_hygiene import clean_tool_result
from agentforge_harness.safety.prompt_injection import mark_tool_result_untrusted
from agentforge_harness.tools.base import Tool, ToolInvocation, ToolResult, ToolKind
from agentforge_harness.utils.redaction import redact_tool_result
import logging

from agentforge_harness.tools.builtin import get_all_builtin_tools
from agentforge_harness.tools.subagents import SubagentRunner, SubagentTool, get_default_subagent_definitions

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self, config: Config):
        self._tools: dict[str, Tool] = {}
        self._mcp_tools: dict[str, Tool] = {}
        self.config = config

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            logger.warning(f"Overwriting existing tools : {tool.name}")

        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def register_mcp_tool(self, tool: Tool) -> None:
        self._mcp_tools[tool.name] = tool
        logger.debug(f"Registered mcp tool: {tool.name}")

    def unregister(self, name: str) -> bool:
        if name in self._tools:
            del self._tools[name]
            return True

        return False

    def get(self, name: str) -> Tool | None:
        if name in self._tools:
            return self._tools[name]
        elif name in self._mcp_tools:
            return self._mcp_tools[name]
        return None

    def get_tools(self, mode: AgentMode | None = None):
        tools: list[Tool] = []

        for tool in self._tools.values():
            tools.append(tool)

        for mcp_tool in self._mcp_tools.values():
            tools.append(mcp_tool)

        if mode == AgentMode.PLAN:
            tools = [
                t for t in tools
                if t.kind in (ToolKind.READ, ToolKind.NETWORK)
            ]

        if self.config.allowed_tools:
            allowed_set = set(self.config.allowed_tools)
            tools = [t for t in tools if t.name in allowed_set]
        return tools

    def get_schemas(self, mode: AgentMode | None = None) -> list[dict[str, Any]]:
        return [tool.to_openai_schema() for tool in self.get_tools(mode=mode)]

    async def _finish_tool_result(
        self,
        hook_system: HookSystem,
        name: str,
        params: dict[str, Any],
        result: ToolResult,
        tool: Tool | None = None,
    ) -> ToolResult:
        if self.config.output_hygiene_enabled:
            result = clean_tool_result(
                result,
                model_name=self.config.model_name,
                max_output_tokens=self.config.max_tool_output_tokens,
            )
        if self.config.redaction_enabled:
            result = redact_tool_result(result)
        if self.config.prompt_injection_protection_enabled and tool is not None:
            result = mark_tool_result_untrusted(
                result,
                tool_name=name,
                tool_kind=tool.kind,
            )
        await hook_system.trigger_after_tool(name, params, result)
        return result

    async def invoke(
        self, 
        name: str, 
        params: dict[str, Any], 
        cwd: Path,
        hook_system : HookSystem,
        approval_manager : ApprovalManager | None = None,
        ) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            result = ToolResult.error_result(
                f"Unknown tool: {name}", metadata={"tool_name": name}
            )
            return await self._finish_tool_result(hook_system, name, params, result)

        validation_errors = tool.validate_params(params)
        if validation_errors:
            result =  ToolResult.error_result(
                f"Invalid Parameter: {'; '.join(validation_errors)}",
                metadata={
                    "tool_name": name,
                    "validation_errors": validation_errors,
                },
            )

            return await self._finish_tool_result(hook_system, name, params, result)


        await hook_system.trigger_before_tool(name, params)
        invocation = ToolInvocation(
            params=params,
            cwd=cwd,
        )
        if approval_manager:
            confirmation = await tool.get_confirmation(invocation)
            if confirmation:
                context = ApprovalContext(
                    tool_name=name,
                    params=params,
                    is_mutating=tool.is_mutating(params),
                    affected_paths=confirmation.affected_paths,
                    command=confirmation.command,
                    is_dangerous=confirmation.is_dangerous,
                )

                decision = await approval_manager.check_approval(context)
                if decision == ApprovalDecision.REJECTED:
                    result = ToolResult.error_result(
                        "Operation rejected by safety policy"
                    )
                    return await self._finish_tool_result(hook_system, name, params, result)
                elif decision == ApprovalDecision.NEEDS_CONFIRMATION:
                    # BUG D fix: request_confirmation is now async; must be awaited.
                    approved = await approval_manager.request_confirmation(confirmation)

                    if not approved:
                        result = ToolResult.error_result("User rejected the operation")
                        return await self._finish_tool_result(hook_system, name, params, result)

        try:
            result = await tool.execute(invocation)
        except Exception as e:
            logger.exception(f"Tool {name} raised unexpected error")
            result = ToolResult.error_result(
                f"Internal error : {str(e)}",
                metadata={
                    "tool_name": name,
                },
            )
        return await self._finish_tool_result(hook_system, name, params, result, tool=tool)


def create_default_registry(
    config: Config,
    subagent_runner: SubagentRunner | None = None,
) -> ToolRegistry:
    from agentforge_harness.tools.subagents import SubagentDefinition

    registry = ToolRegistry(config)

    for tool_class in get_all_builtin_tools():
        registry.register(tool_class(config))

    for subagent_def in get_default_subagent_definitions():
        registry.register(SubagentTool(config, subagent_def, runner=subagent_runner))

    for uc in config.subagents:
        definition = SubagentDefinition(
            name=uc.name,
            description=uc.description,
            goal_prompt=uc.goal_prompt,
            allowed_tools=uc.allowed_tools,
            max_turns=uc.max_turns,
            timeout_seconds=uc.timeout_seconds,
        )
        registry.register(SubagentTool(config, definition, runner=subagent_runner))

    return registry
