import logging
from typing import Any
from agentforge_harness.client.llm_client import LLMClient
from agentforge_harness.client.response import StreamEventType, TokenUsage
from agentforge_harness.context.manager import ContextManager
from agentforge_harness.prompts.system import get_compression_prompt

logger = logging.getLogger(__name__)


class ChatCompactor:
    def __init__(self, client: LLMClient):
        self.client = client

    def _format_history_for_compaction(self, messages: list[dict[str, Any]]) -> str:
        output = ["Here is the conversation that needs to be continue: \n"]

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                continue

            if role == "tool":
                tool_id = msg.get("tool_call_id", "unknown")

                truncated = content[:2000] if len(content) > 2000 else content
                if len(content) > 2000:
                    truncated += "\n... [tool output truncated]"

                output.append(f"[Tool Result ({tool_id})]:\n{truncated}")
            elif role == "assistant":
                tool_details = []
                if content:
                    truncated = content[:3000] if len(content) > 3000 else content
                    if len(content) > 3000:
                        truncated += "\n... [response truncated]"
                    output.append(f"Assistant:\n{truncated}")

                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        func = tc.get("function", {})
                        name = func.get("name", "unknown")
                        args = func.get("arguments", "{}")

                        if len(args) > 500:
                            args = args[:500]
                        tool_details.append(f"  - {name}({args})")

                    output.append("Assistant called tools:\n" + "\n".join(tool_details))
            else:
                truncated = content[:1500] if len(content) > 1500 else content
                if len(content) > 1500:
                    truncated += "\n... [message truncated]"
                output.append(f"User:\n{truncated}")

        return "\n\n---\n\n".join(output)

    async def compress(
        self, context_manager: ContextManager, messages: list[dict[str, Any]] | None = None
    ) -> tuple[str | None, TokenUsage | None]:
        messages = messages or context_manager.get_messages()

        if len(messages) < 3:
            return None, None

        compression_messages = [
            {
                "role": "system",
                "content": get_compression_prompt(),
            },
            {
                "role": "user",
                "content": self._format_history_for_compaction(messages),
            },
        ]

        try:
            summary = ""
            usage = None
            async for event in self.client.chat_completion(
                compression_messages,
                stream=False,
            ):
                if event.type == StreamEventType.TEXT_DELTA and event.text_delta:
                    summary += event.text_delta.content
                elif event.type == StreamEventType.MESSAGE_COMPLETE:
                    usage = event.token_usage

            if not summary or not usage:
                logger.warning(
                    "Compaction produced no usable summary (summary=%s, usage=%s)",
                    bool(summary),
                    bool(usage),
                )
                return None, None

            return summary, usage
        except Exception:
            # Do not swallow silently: a failed compaction means the agent would
            # otherwise keep running over budget. Log it so it is visible; the
            # caller surfaces a user-facing notice and applies a fallback.
            logger.exception("Context compaction failed")
            return None, None
