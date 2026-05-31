from __future__ import annotations

import time

from agentforge_harness.safety.circuit_breaker import CircuitBreakerRegistry, CircuitState


class TestCircuitBreakerBasics:
    def test_new_model_is_closed(self):
        cb = CircuitBreakerRegistry()
        assert cb.get_state("openai/gpt-4o") == CircuitState.CLOSED
        assert cb.can_try("openai/gpt-4o") is True
        assert cb.is_open("openai/gpt-4o") is False

    def test_record_failure_moves_to_open(self):
        cb = CircuitBreakerRegistry(failure_threshold=2)
        cb.record_failure("openai/gpt-4o")
        assert cb.is_open("openai/gpt-4o") is False
        cb.record_failure("openai/gpt-4o")
        assert cb.is_open("openai/gpt-4o") is True
        assert cb.can_try("openai/gpt-4o") is False

    def test_default_threshold(self):
        cb = CircuitBreakerRegistry()
        for _ in range(2):
            cb.record_failure("model/x")
        assert cb.is_open("model/x") is False
        cb.record_failure("model/x")
        assert cb.is_open("model/x") is True

    def test_record_success_resets(self):
        cb = CircuitBreakerRegistry(failure_threshold=2)
        cb.record_failure("m1")
        cb.record_failure("m1")
        assert cb.is_open("m1") is True
        cb.record_success("m1")
        assert cb.is_open("m1") is False
        assert cb.get_state("m1") == CircuitState.CLOSED

    def test_different_models_independent(self):
        cb = CircuitBreakerRegistry(failure_threshold=2)
        cb.record_failure("model/a")
        cb.record_failure("model/a")
        assert cb.is_open("model/a") is True
        assert cb.is_open("model/b") is False


class TestCircuitBreakerResetTimeout:
    def test_auto_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreakerRegistry(failure_threshold=2, reset_timeout=0.01)
        cb.record_failure("m1")
        cb.record_failure("m1")
        assert cb.is_open("m1") is True
        time.sleep(0.02)
        assert cb.is_open("m1") is False
        assert cb.get_state("m1") == CircuitState.HALF_OPEN
        assert cb.can_try("m1") is True

    def test_can_try_returns_true_in_half_open(self):
        cb = CircuitBreakerRegistry(failure_threshold=1, reset_timeout=0.01)
        cb.record_failure("m1")
        assert cb.is_open("m1") is True
        time.sleep(0.02)
        assert cb.can_try("m1") is True
        assert cb.get_state("m1") == CircuitState.HALF_OPEN

    def test_success_in_half_open_closes(self):
        cb = CircuitBreakerRegistry(failure_threshold=1, reset_timeout=0.01)
        cb.record_failure("m1")
        time.sleep(0.02)
        assert cb.get_state("m1") == CircuitState.HALF_OPEN
        cb.record_success("m1")
        assert cb.get_state("m1") == CircuitState.CLOSED


class TestCircuitBreakerReset:
    def test_reset_single_model(self):
        cb = CircuitBreakerRegistry(failure_threshold=1)
        cb.record_failure("m1")
        cb.record_failure("m2")
        assert cb.is_open("m1") is True
        assert cb.is_open("m2") is True
        cb.reset("m1")
        assert cb.is_open("m1") is False
        assert cb.is_open("m2") is True

    def test_reset_all(self):
        cb = CircuitBreakerRegistry(failure_threshold=1)
        cb.record_failure("m1")
        cb.record_failure("m2")
        cb.reset()
        assert cb.is_open("m1") is False
        assert cb.is_open("m2") is False

    def test_reset_unknown_model_noop(self):
        cb = CircuitBreakerRegistry()
        cb.reset("nonexistent")
        assert cb.get_state("nonexistent") == CircuitState.CLOSED


class TestCircuitBreakerEdgeCases:
    def test_success_before_any_failure(self):
        cb = CircuitBreakerRegistry()
        cb.record_success("m1")
        assert cb.get_state("m1") == CircuitState.CLOSED

    def test_many_failures_stays_open(self):
        cb = CircuitBreakerRegistry(failure_threshold=3)
        for _ in range(10):
            cb.record_failure("m1")
        assert cb.is_open("m1") is True
        assert cb.can_try("m1") is False

    def test_get_state_creates_unknown_model(self):
        cb = CircuitBreakerRegistry()
        assert cb.get_state("brand-new") == CircuitState.CLOSED

    def test_is_open_creates_unknown_model(self):
        cb = CircuitBreakerRegistry()
        assert cb.is_open("brand-new") is False

    def test_can_try_creates_unknown_model(self):
        cb = CircuitBreakerRegistry()
        assert cb.can_try("brand-new") is True
