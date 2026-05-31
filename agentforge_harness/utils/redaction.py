from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from agentforge_harness.tools.base import ToolResult


@dataclass
class RedactionReport:
    count: int = 0
    kinds: dict[str, int] = field(default_factory=dict)

    def add(self, kind: str) -> None:
        self.count += 1
        self.kinds[kind] = self.kinds.get(kind, 0) + 1

    def merge(self, other: "RedactionReport") -> None:
        self.count += other.count
        for kind, count in other.kinds.items():
            self.kinds[kind] = self.kinds.get(kind, 0) + count

    def to_metadata(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "kinds": dict(sorted(self.kinds.items())),
        }


@dataclass(frozen=True)
class SecretPattern:
    kind: str
    regex: re.Pattern[str]
    placeholder: str
    preserve_prefix: bool = False


SECRET_PATTERNS: tuple[SecretPattern, ...] = (
    SecretPattern(
        kind="private_key",
        regex=re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        placeholder="[REDACTED:PRIVATE_KEY]",
    ),
    SecretPattern(
        kind="openrouter_api_key",
        regex=re.compile(r"\bsk-or-v1-[A-Za-z0-9_-]{16,}\b"),
        placeholder="[REDACTED:OPENROUTER_API_KEY]",
    ),
    SecretPattern(
        kind="anthropic_api_key",
        regex=re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}\b"),
        placeholder="[REDACTED:ANTHROPIC_API_KEY]",
    ),
    SecretPattern(
        kind="openai_api_key",
        regex=re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
        placeholder="[REDACTED:OPENAI_API_KEY]",
    ),
    SecretPattern(
        kind="github_token",
        regex=re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
        placeholder="[REDACTED:GITHUB_TOKEN]",
    ),
    SecretPattern(
        kind="jwt",
        regex=re.compile(
            r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
        ),
        placeholder="[REDACTED:JWT]",
    ),
    SecretPattern(
        kind="generic_secret_assignment",
        regex=re.compile(
            r"(?P<prefix>\b[A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|AUTHORIZATION)[A-Z0-9_]*\b\s*[:=]\s*[\"']?)(?P<secret>(?!\[REDACTED:)[^\s\"']{8,})",
            re.IGNORECASE,
        ),
        placeholder="[REDACTED:SECRET]",
        preserve_prefix=True,
    ),
)


def redact_text(text: str) -> tuple[str, RedactionReport]:
    report = RedactionReport()
    redacted = text

    for pattern in SECRET_PATTERNS:
        redacted = _replace_pattern(redacted, pattern, report)

    return redacted, report


def _replace_pattern(text: str, pattern: SecretPattern, report: RedactionReport) -> str:
    def replace(match: re.Match[str]) -> str:
        report.add(pattern.kind)
        if pattern.preserve_prefix:
            return f"{match.group('prefix')}{pattern.placeholder}"
        return pattern.placeholder

    return pattern.regex.sub(replace, text)


def redact_value(value: Any) -> tuple[Any, RedactionReport]:
    if isinstance(value, str):
        return redact_text(value)

    if isinstance(value, dict):
        report = RedactionReport()
        redacted_dict: dict[Any, Any] = {}
        for key, item in value.items():
            redacted_item, item_report = redact_value(item)
            report.merge(item_report)
            redacted_dict[key] = redacted_item
        return redacted_dict, report

    if isinstance(value, list):
        return _redact_sequence(value, list)

    if isinstance(value, tuple):
        return _redact_sequence(value, tuple)

    return value, RedactionReport()


def _redact_sequence(
    value: list[Any] | tuple[Any, ...],
    constructor: Callable[[list[Any]], Any],
) -> tuple[Any, RedactionReport]:
    report = RedactionReport()
    redacted_items: list[Any] = []
    for item in value:
        redacted_item, item_report = redact_value(item)
        report.merge(item_report)
        redacted_items.append(redacted_item)
    return constructor(redacted_items), report


def redact_tool_result(result: ToolResult) -> ToolResult:
    report = RedactionReport()
    updates: dict[str, Any] = {}

    for field_name in ("output", "error", "summary", "recovery_hint", "diff_text"):
        value = getattr(result, field_name)
        if value is None:
            continue
        redacted_value, field_report = redact_value(value)
        report.merge(field_report)
        updates[field_name] = redacted_value

    redacted_artifacts, artifacts_report = redact_value(result.artifacts)
    report.merge(artifacts_report)
    updates["artifacts"] = redacted_artifacts

    redacted_next_actions, next_actions_report = redact_value(result.next_actions)
    report.merge(next_actions_report)
    updates["next_actions"] = redacted_next_actions

    redacted_metadata, metadata_report = redact_value(result.metadata)
    report.merge(metadata_report)

    if report.count:
        redacted_metadata = {
            **redacted_metadata,
            "redaction": report.to_metadata(),
        }
    updates["metadata"] = redacted_metadata

    return result.model_copy(update=updates)
