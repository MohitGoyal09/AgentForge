from __future__ import annotations
from datetime import datetime
from agentforge_harness.agent.modes import AgentMode
from agentforge_harness.client.response import TokenUsage
from agentforge_harness.config.config import Config
from agentforge_harness.prompts.system import get_system_prompt
from dataclasses import dataclass, field
from agentforge_harness.utils.text import count_tokens
from typing import Any, TYPE_CHECKING
from agentforge_harness.skills.manager import SkillMetadata

if TYPE_CHECKING:
    from agentforge_harness.context.compaction import ChatCompactor


@dataclass
class MessageItem:
    role: str
    content: str
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    token_count: int | None = None
    pruned_at : datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"role": self.role}

        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id

        if self.tool_calls:
            result["tool_calls"] = self.tool_calls

        if self.content:
            result["content"] = self.content

        return result

    def to_snapshot_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "tool_call_id": self.tool_call_id,
            "tool_calls": self.tool_calls,
            "token_count": self.token_count,
            "pruned_at": self.pruned_at.isoformat() if self.pruned_at else None,
        }

    @classmethod
    def from_snapshot_dict(cls, data: dict[str, Any]) -> MessageItem:
        pruned_at = data.get("pruned_at")
        return cls(
            role=data["role"],
            content=data.get("content", ""),
            tool_call_id=data.get("tool_call_id"),
            tool_calls=data.get("tool_calls", []),
            token_count=data.get("token_count"),
            pruned_at=datetime.fromisoformat(pruned_at) if pruned_at else None,
        )


class ContextManager:
    def __init__(
        self,
        config: Config,
        user_memory: str | None = None,
        tools: list | None = None,
        skills: list[SkillMetadata] | None = None,
        active_skills: list[str] | None = None,
        active_skill_bodies: dict[str, str] | None = None,
        mode: AgentMode = AgentMode.BUILD,
    ):
        self.config = config
        self._user_memory = user_memory
        self._tools = tools or []
        self._skills = skills or []
        self._active_skills = active_skills or []
        self._active_skill_bodies = active_skill_bodies or {}
        self._mode = mode
        self._system_prompt = get_system_prompt(
            config=config,
            user_memory=user_memory,
            tools=tools,
            skills=self._skills,
            active_skills=self._active_skills,
            active_skill_bodies=self._active_skill_bodies,
            mode=mode,
        )
        self._model_name = self.config.model_name
        self._prune_protect_tokens: int = config.max_tool_output_tokens
        self._prune_minimum_tokens: int = config.max_tool_output_tokens // 2
        self._messages: list[MessageItem] = []
        self._latest_usage = TokenUsage()
        self._total_usage = TokenUsage()

    def set_model_name(self, model_name: str) -> None:
        self._model_name = model_name
        for message in self._messages:
            message.token_count = count_tokens(message.content, self._model_name)

    def add_user_message(self, content: str) -> None:
        item = MessageItem(
            role="user",
            content=content,
            token_count=count_tokens(content, self._model_name),
        )
        self._messages.append(item)

    def add_assistant_message(
        self, content: str, tool_calls: list[dict[str, Any]]
    ) -> None:
        item = MessageItem(
            role="assistant",
            content=content or "",
            token_count=count_tokens(content or "", self._model_name),
            tool_calls=tool_calls or [],
        )
        self._messages.append(item)

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        item = MessageItem(
            role="tool",
            content=content,
            tool_call_id=tool_call_id,
            token_count=count_tokens(content, self._model_name),
        )
        self._messages.append(item)

    def get_messages(self) -> list[dict[str, Any]]:
        messages = []
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})

        for item in self._messages:
            messages.append(item.to_dict())
        return messages
    
    # Context-budget tiers (percent of the model context window).
    _WARNING_THRESHOLD_PCT = 70
    _COMPACT_THRESHOLD_PCT = 80
    _CRITICAL_THRESHOLD_PCT = 95

    def get_context_budget(self) -> dict:
        window = self.config.model.context_window
        total = self._estimate_current_tokens()
        pct = (total / window * 100) if window > 0 else 0
        return {
            "total_tokens": total,
            "context_window": window,
            "usage_pct": round(pct, 1),
            "remaining": window - total,
            "warning": pct >= self._WARNING_THRESHOLD_PCT,
            # should_compact is the actionable trigger: compact before we run
            # out of room, not after we have already overrun the window.
            "should_compact": pct >= self._COMPACT_THRESHOLD_PCT,
            # critical means dangerously full — compaction is now urgent.
            "critical": pct >= self._CRITICAL_THRESHOLD_PCT,
        }

    def needs_compression(self) -> bool:
        return self.get_context_budget()["should_compact"]

    def _estimate_current_tokens(self) -> int:
        total = 0
        if self._system_prompt:
            total += count_tokens(self._system_prompt, self._model_name)
        for msg in self._messages:
            total += msg.token_count or count_tokens(msg.content, self._model_name)
        return total
    
    def set_latest_usage(self, usage: TokenUsage):
        self._latest_usage = usage

    def add_usage(self, usage: TokenUsage):
        self._total_usage += usage
    
    _KEEP_RECENT_TURNS = 5

    def replace_with_summary(self, summary: str, recent_messages: list[MessageItem] | None = None) -> None:
        continuation_content = f"""# Context Restoration (Previous Session Compacted)

The previous conversation was compacted due to context length limits.

{summary}

**CRITICAL: Actions listed above as completed are already done. DO NOT repeat them.**"""

        self._messages = [MessageItem(
            role="user",
            content=continuation_content,
            token_count=count_tokens(continuation_content, self._model_name),
        )]

        if recent_messages:
            self._messages.extend(recent_messages)

    async def compress_old_messages(self, compactor: ChatCompactor) -> tuple[str | None, TokenUsage | None]:
        if len(self._messages) <= self._KEEP_RECENT_TURNS:
            return None, None

        split_index = len(self._messages) - self._KEEP_RECENT_TURNS
        recent_messages = self._messages[split_index:]
        old_messages = self._messages[:split_index]

        old_dicts = [message.to_dict() for message in old_messages]

        summary, usage = await compactor.compress(self, messages=old_dicts)

        if summary:
            self.replace_with_summary(summary, recent_messages=recent_messages)

        return summary, usage
    
    def prune_tool_outputs(self) -> int:
        user_message_count = sum(1 for msg in self._messages if msg.role == 'user')

        if user_message_count < 2 :
            return 0
        
        protected_tokens = 0
        pruned_tokens = 0
        to_prune : list[MessageItem]= []
        for msg in reversed(self._messages):
            if msg.role == 'tool' and msg.tool_call_id:
                if msg.pruned_at:
                    continue

                tokens = msg.token_count or count_tokens(msg.content , self._model_name)
                if protected_tokens < self._prune_protect_tokens:
                    protected_tokens += tokens
                    continue

                pruned_tokens += tokens
                to_prune.append(msg)

        if pruned_tokens < self._prune_minimum_tokens:
            return 0
        
        pruned_count = 0

        for msg in to_prune:
            msg.content ="[Old tool result content cleared]"
            msg.token_count = count_tokens(msg.content , self._model_name)
            msg.pruned_at = datetime.now()
            pruned_count +=1

        return pruned_count
    
    def clear(self) -> None:
        self._messages = []

    def snapshot_messages(self) -> list[dict[str, Any]]:
        return [message.to_snapshot_dict() for message in self._messages]

    def restore_messages(self, messages: list[dict[str, Any]]) -> None:
        self._messages = [MessageItem.from_snapshot_dict(message) for message in messages]

    def get_latest_usage(self) -> TokenUsage:
        return self._latest_usage

    def get_total_usage(self) -> TokenUsage:
        return self._total_usage

    def restore_usage(self, latest_usage: TokenUsage, total_usage: TokenUsage) -> None:
        self._latest_usage = latest_usage
        self._total_usage = total_usage

    def refresh_system_prompt(
        self,
        skills: list[SkillMetadata] | None = None,
        active_skills: list[str] | None = None,
        active_skill_bodies: dict[str, str] | None = None,
        mode: AgentMode | None = None,
        tools: list | None = None,
    ) -> None:
        if skills is not None:
            self._skills = skills
        if active_skills is not None:
            self._active_skills = active_skills
        if active_skill_bodies is not None:
            self._active_skill_bodies = active_skill_bodies
        if mode is not None:
            self._mode = mode
        if tools is not None:
            self._tools = tools

        self._system_prompt = get_system_prompt(
            config=self.config,
            user_memory=self._user_memory,
            tools=self._tools,
            skills=self._skills,
            active_skills=self._active_skills,
            active_skill_bodies=self._active_skill_bodies,
            mode=self._mode,
        )



    
