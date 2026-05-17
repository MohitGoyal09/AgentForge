from pydantic import BaseModel , Field
from config.config import Config
from tools.base import Tool, ToolInvocation, ToolResult
from dataclasses import dataclass
from typing import Any
import asyncio

class SubagentParams(BaseModel):
    goal: str = Field(
        ..., description="The specific task or goal for the subagent to accomplish"
    )


@dataclass
class SubagentDefinition:
    name: str
    description: str
    goal_prompt: str
    allowed_tools: list[str] | None = None
    max_turns: int = 20
    timeout_seconds: float = 600


class SubagentTool(Tool):
    def __init__(self, config: Config, definition: SubagentDefinition):
        super().__init__(config)
        self.definition = definition

    @property
    def name(self) -> str:
        return f"subagent_{self.definition.name}"

    @property
    def description(self) -> str:
        return f"subagent_{self.definition.description}"

    schema = SubagentParams

    def is_mutating(self, params: dict[str, Any]) -> bool:
        return True
    
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        from agent.agent import Agent
        from agent.events import AgentEventType

        params = SubagentParams(**invocation.params)
        if not params.goal:
            return ToolResult.error_result("No goal specified for sub-agent")
        
        config_dict = self.config.to_dict()
        config_dict['max_turns'] = self.definition.max_turns
        if self.definition.allowed_tools:
            config_dict['allowed_tools'] = self.definition.allowed_tools
        
        subagent_config = Config(**config_dict)

        prompt = f"""You are a specialized sub-agent with a specific task to complete.

        {self.definition.goal_prompt}

        YOUR TASK:
        {params.goal}

        IMPORTANT:
        - Focus only on completing the specified task
        - Do not engage in unrelated actions
        - Once you have completed the task or have the answer, provide your final response
        - Be concise and direct in your output
        """

        tool_calls: list[str] = []
        streamed_text: str = ""
        final_response = None
        error = None
        terminate_response = "goal"

       
        event_handler = getattr(invocation, '_event_handler', None)

        try:
            async with Agent(subagent_config) as agent:
                deadline = (
                    asyncio.get_event_loop().time() + self.definition.timeout_seconds
                )
                async for event in agent.run(prompt):
                    if asyncio.get_event_loop().time() > deadline:
                        terminate_response = "timeout"
                        final_response = "Sub-agent timed out"
                        break

                    if event_handler:
                        await event_handler(event)

                    if event.type == AgentEventType.TEXT_DELTA:
                        streamed_text += event.data.get("content", "")
                    elif event.type == AgentEventType.TOOL_CALL_START:
                        tool_calls.append(event.data.get("name", "unknown"))
                    elif event.type == AgentEventType.TEXT_COMPLETE:
                        final_response = event.data.get("content") or streamed_text
                    elif event.type == AgentEventType.AGENT_END:
                        final_response = final_response or event.data.get("response") or streamed_text
                    elif event.type == AgentEventType.AGENT_ERROR:
                        terminate_response = "error"
                        error = event.data.get('error', 'Unknown')
                        final_response = f"Sub-agent error: {error}"
                        break
        except Exception as e:
            terminate_response = "error"
            error = str(e)
            final_response = f"Sub-agent failed: {e}"

        display_text = final_response or streamed_text or "No response"
        tools_summary = ", ".join(tool_calls) if tool_calls else "None"
        result = (
            f"Sub-agent '{self.definition.name}' completed\n"
            f"Termination: {terminate_response}\n"
            f"Tools called: {tools_summary}\n"
            f"\n{display_text}"
        )

        if error:
            return ToolResult.error_result(result)

        return ToolResult.success_result(result)
    



CODEBASE_INVESTIGATOR = SubagentDefinition(
    name="codebase_investigator",
    description="Investigates the codebase to answer questions about code structure, patterns, and implementations",
    goal_prompt="""You are a codebase investigation specialist.
Your job is to explore and understand code to answer questions.
Use read_file, grep, glob, and list_dir to investigate.
Do NOT modify any files.""",
    allowed_tools=["read_file", "grep", "glob", "list_dir"],
)

CODE_REVIEWER = SubagentDefinition(
    name="code_reviewer",
    description="Reviews code changes and provides feedback on quality, bugs, and improvements",
    goal_prompt="""You are a code review specialist.
Your job is to review code and provide constructive feedback.
Look for bugs, code smells, security issues, and improvement opportunities.
Use read_file, list_dir and grep to examine the code.
Do NOT modify any files.""",
    allowed_tools=["read_file", "grep", "list_dir"],
    max_turns=10,
    timeout_seconds=300,
)


def get_default_subagent_definitions() -> list[SubagentDefinition]:
    return [
        CODEBASE_INVESTIGATOR,
        CODE_REVIEWER,
    ]