from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field


@dataclass
class SteeringQueue:
    _steer: deque[str] = field(default_factory=deque)
    _follow_up: deque[str] = field(default_factory=deque)

    def push_steer(self, text: str) -> None:
        self._steer.append(text)

    def push_follow_up(self, text: str) -> None:
        self._follow_up.append(text)

    def pop_steer(self) -> str | None:
        return self._steer.popleft() if self._steer else None

    def pop_follow_up(self) -> str | None:
        return self._follow_up.popleft() if self._follow_up else None

    def snapshot(self) -> dict:
        return {"steer": list(self._steer), "follow_up": list(self._follow_up)}

    def clear(self) -> None:
        self._steer.clear()
        self._follow_up.clear()
