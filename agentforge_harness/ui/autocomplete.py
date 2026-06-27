from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CompletionItem:
    display: str
    replacement: str
    start: int
    end: int
    description: str = ""

    def apply(self, text: str) -> str:
        return f"{text[:self.start]}{self.replacement}{text[self.end:]}"


@dataclass(frozen=True, slots=True)
class CompletionState:
    items: tuple[CompletionItem, ...] = ()
    selected_index: int = 0

    @property
    def selected(self) -> CompletionItem | None:
        if not self.items:
            return None
        return self.items[self.selected_index]

    def select_next(self) -> CompletionState:
        if not self.items:
            return self
        return CompletionState(
            items=self.items,
            selected_index=(self.selected_index + 1) % len(self.items),
        )

    def select_previous(self) -> CompletionState:
        if not self.items:
            return self
        return CompletionState(
            items=self.items,
            selected_index=(self.selected_index - 1) % len(self.items),
        )


def build_completion_state(
    text: str,
    *,
    commands: list[str],
    cwd: Path | None = None,
) -> CompletionState:
    if not text.startswith("/"):
        return CompletionState()
    prefix = text.lower()
    matched = [
        CompletionItem(
            display=cmd,
            replacement=cmd,
            start=0,
            end=len(text),
        )
        for cmd in sorted(commands)
        if cmd.lower().startswith(prefix)
    ]
    return CompletionState(items=tuple(matched))
