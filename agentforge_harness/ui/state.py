from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

ChatItemRole = Literal["user", "assistant", "tool", "error", "status", "thinking"]


@dataclass
class ChatItem:
    role: ChatItemRole
    text: str
    tool_call_id: str = ""
    always_show: bool = False


@dataclass
class TuiState:
    items: list[ChatItem] = field(default_factory=list)
    assistant_buffer: str = ""
    thinking_buffer: str = ""
    running: bool = False
    show_thinking: bool = False
    show_tool_results: bool = True

    def add_user_message(self, text: str) -> None:
        self.items.append(ChatItem(role="user", text=text))

    def flush_assistant_delta(self, delta: str) -> None:
        self.assistant_buffer += delta
        existing = [i for i in self.items if i.role == "assistant"]
        if existing:
            existing[-1].text = self.assistant_buffer
        else:
            self.items.append(ChatItem(role="assistant", text=self.assistant_buffer))

    def finalize_assistant(self) -> None:
        self.assistant_buffer = ""

    def flush_thinking_delta(self, delta: str) -> None:
        self.thinking_buffer += delta
        existing = [i for i in self.items if i.role == "thinking"]
        if existing:
            existing[-1].text = self.thinking_buffer
        else:
            self.items.append(ChatItem(role="thinking", text=self.thinking_buffer))

    def finalize_thinking(self) -> None:
        self.thinking_buffer = ""

    def add_tool_item(self, call_id: str, name: str, args: dict) -> None:
        text = f"[{name}] {json.dumps(args, ensure_ascii=False)[:200]}"
        self.items.append(ChatItem(role="tool", text=text, tool_call_id=call_id))

    def update_tool_result(self, call_id: str, output: str, success: bool) -> None:
        for item in reversed(self.items):
            if item.role == "tool" and item.tool_call_id == call_id:
                status = "✓" if success else "✗"
                item.text = item.text.split("\n")[0] + f"\n{status} {output[:300]}"
                return

    def add_error(self, text: str) -> None:
        self.items.append(ChatItem(role="error", text=text))

    def add_status(self, text: str) -> None:
        self.items.append(ChatItem(role="status", text=text))

    def toggle_thinking(self) -> None:
        self.show_thinking = not self.show_thinking

    def toggle_tool_results(self) -> None:
        self.show_tool_results = not self.show_tool_results

    def clear(self) -> None:
        self.items.clear()
        self.assistant_buffer = ""
        self.thinking_buffer = ""
        self.running = False
