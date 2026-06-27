from __future__ import annotations

from enum import Enum


class ThinkingLevel(str, Enum):
    """Reasoning effort levels, mapped per-provider to native parameters."""

    OFF = "off"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


# Anthropic extended-thinking token budgets per level (None = thinking disabled).
_ANTHROPIC_BUDGET: dict[ThinkingLevel, int] = {
    ThinkingLevel.MINIMAL: 1024,
    ThinkingLevel.LOW: 2048,
    ThinkingLevel.MEDIUM: 4096,
    ThinkingLevel.HIGH: 8192,
    ThinkingLevel.XHIGH: 16384,
}

# OpenAI-style reasoning_effort per level (None = omit the parameter).
_OPENAI_EFFORT: dict[ThinkingLevel, str] = {
    ThinkingLevel.MINIMAL: "minimal",
    ThinkingLevel.LOW: "low",
    ThinkingLevel.MEDIUM: "medium",
    ThinkingLevel.HIGH: "high",
    ThinkingLevel.XHIGH: "high",  # providers cap at "high"
}


def anthropic_thinking_budget(level: ThinkingLevel) -> int | None:
    """Token budget for Anthropic extended thinking, or None when disabled."""
    return _ANTHROPIC_BUDGET.get(level)


def openai_reasoning_effort(level: ThinkingLevel) -> str | None:
    """reasoning_effort value for OpenAI-compatible reasoning models, or None."""
    return _OPENAI_EFFORT.get(level)


def is_enabled(level: ThinkingLevel) -> bool:
    return level != ThinkingLevel.OFF
