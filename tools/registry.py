from pathlib import Path
from typing import Any
from config.config import Config
from tools.base import Tool, ToolInvocation, ToolResult
import logging

from tools.builtin import get_all_builtin_tools
from tools.subagents import SubagentTool, get_default_subagent_definitions

logger = logging.getLogger(__name__)

class ToolRegistry:
    def __init__(self , config : Config):
        self._tools : dict [str , Tool] = {}
        self.config = config
    
    def register(self , tool : Tool) -> None:
        if tool.name in self._tools:
            logger.warning(f"Overwriting existing tools : {tool.name}")
        
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def unregister(self , name : str) -> bool:
        if name in self._tools:
            del self._tools[name]
            return True
        
        return False
    
    def get(self , name : str) -> Tool | None:
        if name in self._tools:
            return self._tools[name]
        return None

    def get_tools(self):
        tools : list[Tool] = []

        for tool in self._tools.values():
            tools.append(tool)
        
        if self.config.allowed_tools:
            allowed_set = set(self.config.allowed_tools)
            tools = [ t for t in tools if t.name in allowed_set]
        return tools


    def get_schemas(self) -> list[dict[str , Any]]:
        return [tool.to_openai_schema() for tool in self.get_tools()]

    async def invoke(self , name : 
        str , params : dict[str , Any] ,
        cwd : Path ) ->  ToolResult :

         
        tool = self.get(name)
        if tool is None:
            return ToolResult.error_result(
                f'Unkown tool: {name}',
                metadata = {
                    "tool_name" : name
                }
            )
        
        validation_errors = tool.validate_params(params)
        if validation_errors:
            return ToolResult.error_result(
                f"Invalid Parametere : {'; '.join(validation_errors)}",
                metadata = {
                    "tool_name" : name,
                    "validation_errors" : validation_errors,
                },
            )
       
        invocation = ToolInvocation(
            params = params,
            cwd = cwd,
        )
        
        try : 
           result = await tool.execute(invocation)
           return result
        except Exception as e:
            logger.exception(f"Tool {name} raised unexpected error")
            return ToolResult.error_result(
                f"Internal error : {str(e)}" ,
                metadata = {
                    "tool_name": name,
                }
            )

def create_default_registery(config : Config) -> ToolRegistry:
    from tools.subagents import SubagentDefinition

    registry = ToolRegistry(config)
    
    for tool_class in get_all_builtin_tools():
        registry.register(tool_class(config))
    
    for subagent_def in get_default_subagent_definitions():
        registry.register(SubagentTool(config, subagent_def))

  
    for uc in config.subagents:
        definition = SubagentDefinition(
            name=uc.name,
            description=uc.description,
            goal_prompt=uc.goal_prompt,
            allowed_tools=uc.allowed_tools,
            max_turns=uc.max_turns,
            timeout_seconds=uc.timeout_seconds,
        )
        registry.register(SubagentTool(config, definition))

    return registry



 
