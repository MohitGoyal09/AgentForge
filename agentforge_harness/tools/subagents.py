from pydantic import BaseModel , Field
from agentforge_harness.config.config import Config
from agentforge_harness.agent.events import AgentEvent, AgentEventType
from agentforge_harness.tools.base import Tool, ToolInvocation, ToolResult
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable
import asyncio

# A runner produces the event stream for a subagent run, given the subagent's
# config and prompt. Injected by the composition root so the tools layer never
# imports the Agent class (which would re-introduce the agent <-> tools cycle).
SubagentRunner = Callable[[Config, str], AsyncIterator[AgentEvent]]


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
    def __init__(
        self,
        config: Config,
        definition: SubagentDefinition,
        runner: SubagentRunner | None = None,
    ):
        super().__init__(config)
        self.definition = definition
        self._runner = runner

    @property
    def name(self) -> str:
        return f"subagent_{self.definition.name}"

    @property
    def description(self) -> str:
        return f"Run the {self.definition.name} subagent: {self.definition.description}"

    schema = SubagentParams

    def is_mutating(self, params: dict[str, Any]) -> bool:
        if self.definition.allowed_tools is None:
            return True

        mutating_tools = {
            "edit",
            "write_file",
            "shell",
            "web_search",
            "web_fetch",
            "memory",
            "todos",
        }
        return any(tool_name in mutating_tools for tool_name in self.definition.allowed_tools)
    
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        if self._runner is None:
            return ToolResult.error_result(
                "Subagent runner is not configured for this tool"
            )

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


        event_handler = invocation._event_handler

        try:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self.definition.timeout_seconds
            runner_iter = self._runner(subagent_config, prompt).__aiter__()
            # BUG F fix: wrap each __anext__ call in asyncio.wait_for so a stalled
            # runner is interrupted by the timeout rather than waiting indefinitely
            # between events.
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    terminate_response = "timeout"
                    final_response = "Sub-agent timed out"
                    break
                try:
                    event = await asyncio.wait_for(
                        runner_iter.__anext__(), timeout=remaining
                    )
                except asyncio.TimeoutError:
                    terminate_response = "timeout"
                    final_response = "Sub-agent timed out"
                    break
                except StopAsyncIteration:
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
    



EXPLORE = SubagentDefinition(
    name="explore",
    description="Maps unfamiliar code and finds the files, symbols, and patterns relevant to a task",
    goal_prompt="""You are a codebase exploration specialist.
Your job is to quickly map unfamiliar code and identify the most relevant files, symbols, data flow, and architectural patterns.
Return concise findings with file paths and short reasons why each file matters.
Use read_file, grep, glob, and list_dir to investigate.
Do NOT modify any files.""",
    allowed_tools=["read_file", "grep", "glob", "list_dir"],
    max_turns=12,
    timeout_seconds=300,
)

DEBUGGER = SubagentDefinition(
    name="debugger",
    description="Investigates likely root causes for bugs without changing files",
    goal_prompt="""You are a debugging specialist.
Your job is to trace symptoms to likely root causes using the codebase evidence available to you.
Prefer concrete file/function references, explain the failure path, and suggest the smallest safe fix.
Use read_file, grep, glob, and list_dir to investigate.
Do NOT modify any files.""",
    allowed_tools=["read_file", "grep", "glob", "list_dir"],
    max_turns=14,
    timeout_seconds=360,
)

CODE_REVIEWER = SubagentDefinition(
    name="code_reviewer",
    description="Reviews code changes and provides feedback on quality, bugs, and improvements",
    goal_prompt="""You are a code review specialist.
Your job is to review code and provide constructive feedback.
Look for bugs, code smells, security issues, and improvement opportunities.
Lead with concrete findings grounded in file paths and behavior.
Use read_file, list_dir, glob, and grep to examine the code.
Do NOT modify any files.""",
    allowed_tools=["read_file", "grep", "glob", "list_dir"],
    max_turns=10,
    timeout_seconds=300,
)

TEST_PLANNER = SubagentDefinition(
    name="test_planner",
    description="Designs focused verification plans for a change",
    goal_prompt="""You are a test planning specialist.
Your job is to inspect the codebase and propose the smallest useful verification plan for the requested change.
Identify existing test commands, risky paths, missing coverage, and a practical smoke-test sequence.
Use read_file, grep, glob, and list_dir to investigate.
Do NOT modify any files.""",
    allowed_tools=["read_file", "grep", "glob", "list_dir"],
    max_turns=10,
    timeout_seconds=300,
)

ARCHITECT = SubagentDefinition(
    name="architect",
    description="Explains architecture boundaries and suggests design-level changes",
    goal_prompt="""You are an architecture analysis specialist.
Your job is to explain module boundaries, ownership, data flow, and design trade-offs.
Focus on how a proposed change fits the existing architecture and where the harness contract should live.
Use read_file, grep, glob, and list_dir to investigate.
Do NOT modify any files.""",
    allowed_tools=["read_file", "grep", "glob", "list_dir"],
    max_turns=12,
    timeout_seconds=300,
)

CODEBASE_INVESTIGATOR = SubagentDefinition(
    name="codebase_investigator",
    description="Investigates the codebase to answer questions about code structure, patterns, and implementations",
    goal_prompt="""You are a codebase investigation specialist.
Your job is to explore and understand code to answer questions.
Use read_file, grep, glob, and list_dir to investigate.
Do NOT modify any files.""",
    allowed_tools=["read_file", "grep", "glob", "list_dir"],
)


def get_default_subagent_definitions() -> list[SubagentDefinition]:
    return [
        EXPLORE,
        DEBUGGER,
        CODEBASE_INVESTIGATOR,
        CODE_REVIEWER,
        TEST_PLANNER,
        ARCHITECT,
    ]
