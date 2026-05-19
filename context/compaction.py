from typing import Any
from client.llm_client import LLMClient
from client.response import StreamEventType, TokenUsage
from context.manager import ContextManager
from prompts.system import get_compression_prompt


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
        self, context_manager: ContextManager
    ) -> tuple[str | None, TokenUsage | None]:
        messages = context_manager.get_messages()

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
                if event.type == StreamEventType.MESSAGE_COMPLETE:
                    usage = event.usage
                    summary += event.text_delta.content

            if not summary or not usage:
                return None, None

            return summary, usage
        except Exception:
            return None, None