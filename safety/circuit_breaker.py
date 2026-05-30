from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class _BreakerState:
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0


class CircuitBreakerRegistry:
    def __init__(self, failure_threshold: int = 3, reset_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._breakers: dict[str, _BreakerState] = {}

    def _get_or_create(self, model_name: str) -> _BreakerState:
        if model_name not in self._breakers:
            self._breakers[model_name] = _BreakerState()
        return self._breakers[model_name]

    def record_failure(self, model_name: str) -> None:
        state = self._get_or_create(model_name)
        state.failure_count += 1
        state.last_failure_time = time.time()
        if state.failure_count >= self.failure_threshold:
            state.state = CircuitState.OPEN

    def record_success(self, model_name: str) -> None:
        state = self._get_or_create(model_name)
        state.failure_count = 0
        state.state = CircuitState.CLOSED

    def can_try(self, model_name: str) -> bool:
        state = self._get_or_create(model_name)
        if state.state == CircuitState.CLOSED:
            return True
        if state.state == CircuitState.OPEN:
            elapsed = time.time() - state.last_failure_time
            if elapsed >= self.reset_timeout:
                state.state = CircuitState.HALF_OPEN
                return True
            return False
        return True

    def get_state(self, model_name: str) -> CircuitState:
        state = self._get_or_create(model_name)
        if state.state == CircuitState.OPEN:
            elapsed = time.time() - state.last_failure_time
            if elapsed >= self.reset_timeout:
                state.state = CircuitState.HALF_OPEN
        return state.state

    def is_open(self, model_name: str) -> bool:
        state = self._get_or_create(model_name)
        if state.state != CircuitState.OPEN:
            return False
        elapsed = time.time() - state.last_failure_time
        if elapsed >= self.reset_timeout:
            state.state = CircuitState.HALF_OPEN
            return False
        return True

    def reset(self, model_name: str | None = None) -> None:
        if model_name:
            self._breakers.pop(model_name, None)
        else:
            self._breakers.clear()
