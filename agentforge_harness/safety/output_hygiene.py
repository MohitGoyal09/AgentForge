from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from agentforge_harness.tools.base import ToolResult
from agentforge_harness.utils.text import count_tokens, truncate_text


ANSI_ESCAPE_RE = re.compile(
    r"(?:\x1B\[[0-?]*[ -/]*[@-~]|\x1B\][^\x07]*(?:\x07|\x1B\\)|\x1B[@-Z\\-_])"
)
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]")
TRUNCATABLE_RESULT_FIELDS = ("output", "error", "summary", "recovery_hint", "diff_text")


@dataclass
class OutputHygieneReport:
    ansi_sequences_removed: int = 0
    control_chars_removed: int = 0
    truncated_fields: dict[str, int] = field(default_factory=dict)

    def merge(self, other: "OutputHygieneReport") -> None:
        self.ansi_sequences_removed += other.ansi_sequences_removed
        self.control_chars_removed += other.control_chars_removed
        for field_name, count in other.truncated_fields.items():
            self.truncated_fields[field_name] = (
                self.truncated_fields.get(field_name, 0) + count
            )

    @property
    def changed(self) -> bool:
        return bool(
            self.ansi_sequences_removed
            or self.control_chars_removed
            or self.truncated_fields
        )

    def to_metadata(self) -> dict[str, Any]:
        return {
            "ansi_sequences_removed": self.ansi_sequences_removed,
            "control_chars_removed": self.control_chars_removed,
            "truncated_fields": dict(sorted(self.truncated_fields.items())),
        }


def clean_text(text: str) -> tuple[str, OutputHygieneReport]:
    report = OutputHygieneReport()

    ansi_matches = ANSI_ESCAPE_RE.findall(text)
    if ansi_matches:
        report.ansi_sequences_removed += len(ansi_matches)
        text = ANSI_ESCAPE_RE.sub("", text)

    control_matches = CONTROL_CHAR_RE.findall(text)
    if control_matches:
        report.control_chars_removed += len(control_matches)
        text = CONTROL_CHAR_RE.sub("", text)

    return text, report


def clean_value(value: Any) -> tuple[Any, OutputHygieneReport]:
    if isinstance(value, str):
        return clean_text(value)

    if isinstance(value, dict):
        report = OutputHygieneReport()
        cleaned_dict: dict[Any, Any] = {}
        for key, item in value.items():
            cleaned_item, item_report = clean_value(item)
            report.merge(item_report)
            cleaned_dict[key] = cleaned_item
        return cleaned_dict, report

    if isinstance(value, list):
        return _clean_sequence(value, list)

    if isinstance(value, tuple):
        return _clean_sequence(value, tuple)

    return value, OutputHygieneReport()


def clean_tool_result(
    result: ToolResult,
    *,
    model_name: str,
    max_output_tokens: int,
) -> ToolResult:
    report = OutputHygieneReport()
    updates: dict[str, Any] = {}

    for field_name in TRUNCATABLE_RESULT_FIELDS:
        value = getattr(result, field_name)
        if value is None:
            continue
        cleaned_value, field_report = clean_text(value)
        report.merge(field_report)
        truncated_value = _truncate_field(
            cleaned_value,
            field_name=field_name,
            model_name=model_name,
            max_output_tokens=max_output_tokens,
            report=report,
        )
        updates[field_name] = truncated_value

    cleaned_artifacts, artifacts_report = clean_value(result.artifacts)
    report.merge(artifacts_report)
    updates["artifacts"] = cleaned_artifacts

    cleaned_next_actions, next_actions_report = clean_value(result.next_actions)
    report.merge(next_actions_report)
    updates["next_actions"] = cleaned_next_actions

    cleaned_metadata, metadata_report = clean_value(result.metadata)
    report.merge(metadata_report)

    if report.changed:
        cleaned_metadata = {
            **cleaned_metadata,
            "output_hygiene": report.to_metadata(),
        }
    updates["metadata"] = cleaned_metadata

    return result.model_copy(update=updates)


def _clean_sequence(
    value: list[Any] | tuple[Any, ...],
    constructor: Callable[[list[Any]], Any],
) -> tuple[Any, OutputHygieneReport]:
    report = OutputHygieneReport()
    cleaned_items: list[Any] = []
    for item in value:
        cleaned_item, item_report = clean_value(item)
        report.merge(item_report)
        cleaned_items.append(cleaned_item)
    return constructor(cleaned_items), report


def _truncate_field(
    value: str,
    *,
    field_name: str,
    model_name: str,
    max_output_tokens: int,
    report: OutputHygieneReport,
) -> str:
    if max_output_tokens <= 0:
        return value

    before_tokens = count_tokens(value, model_name)
    if before_tokens <= max_output_tokens:
        return value

    truncated = truncate_text(
        value,
        model_name,
        max_output_tokens,
        suffix="\n... [tool output truncated by AgentForge]",
    )
    removed_tokens = max(1, before_tokens - count_tokens(truncated, model_name))
    report.truncated_fields[field_name] = (
        report.truncated_fields.get(field_name, 0) + removed_tokens
    )
    return truncated
