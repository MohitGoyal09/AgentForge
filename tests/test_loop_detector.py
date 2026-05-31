from __future__ import annotations

from agentforge_harness.context.loop_detector import LoopDetector


class TestLoopDetector:
    def test_empty_history_returns_no_loop(self):
        ld = LoopDetector()
        assert ld.check_for_loop() is None

    def test_single_action_returns_no_loop(self):
        ld = LoopDetector()
        ld.record_action("response", text="hello")
        assert ld.check_for_loop() is None

    def test_exact_repeat_triggers(self):
        ld = LoopDetector()
        ld.record_action("tool_call", tool_name="read_file", args={"path": "x"})
        ld.record_action("tool_call", tool_name="read_file", args={"path": "x"})
        result = ld.check_for_loop()
        assert result is None

        ld.record_action("tool_call", tool_name="read_file", args={"path": "x"})
        result = ld.check_for_loop()
        assert result is not None
        assert "repeated" in result

    def test_different_args_do_not_trigger(self):
        ld = LoopDetector()
        ld.record_action("tool_call", tool_name="read_file", args={"path": "a"})
        ld.record_action("tool_call", tool_name="read_file", args={"path": "b"})
        ld.record_action("tool_call", tool_name="read_file", args={"path": "a"})
        assert ld.check_for_loop() is None

    def test_cycle_detection(self):
        ld = LoopDetector()
        for _ in range(2):
            ld.record_action("tool_call", tool_name="read_file", args={"path": "x"})
            ld.record_action("tool_call", tool_name="grep", args={"pattern": "y"})
        result = ld.check_for_loop()
        assert result is not None
        assert "cycle" in result

    def test_clear_resets(self):
        ld = LoopDetector()
        for _ in range(3):
            ld.record_action("response", text="hello")
        assert ld.check_for_loop() is not None
        ld.clear()
        assert ld.check_for_loop() is None

    def test_response_text_truncated(self):
        ld = LoopDetector()
        long_text = "word " * 1000
        ld.record_action("response", text=long_text)
        assert len(ld._history[0]) < len(long_text)

    def test_mixed_actions_do_not_false_positive(self):
        ld = LoopDetector()
        ld.record_action("response", text="analyzing")
        ld.record_action("tool_call", tool_name="read_file", args={"path": "a"})
        ld.record_action("response", text="found it")
        ld.record_action("tool_call", tool_name="grep", args={"pattern": "b"})
        assert ld.check_for_loop() is None

    def test_exact_response_repeat_triggers(self):
        ld = LoopDetector()
        for _ in range(3):
            ld.record_action("response", text="I don't know")
        assert ld.check_for_loop() is not None
