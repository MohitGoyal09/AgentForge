from collections import deque
import json
from typing import Any


class LoopDetector:
    def __init__(self) -> None:
        self.max_exact_repeats = 3
        self.max_cycle_length = 5
        self._history: deque[str] = deque(maxlen=20)

    def record_action(self, action_type: str, **details: Any) -> None:
        output = [action_type]

        if action_type == "tool_call":
            output.append(details.get("tool_name", ""))
            args = details.get("args", {})

            if isinstance(args, dict):
                for k in sorted(args.keys()):
                    value = json.dumps(args[k], sort_keys=True, default=str)
                    output.append(f"{k}={value}")

        elif action_type == "response":
            text = " ".join(details.get("text", "").split())
            output.append(text[:500])

        signature = "|".join(output)
        self._history.append(signature)

    def check_for_loop(self) -> str | None:
        if len(self._history) < 2:
            return None

        if len(self._history) >= self.max_exact_repeats:
            recent = list(self._history)[-self.max_exact_repeats:]
            if len(set(recent)) == 1:
                return f"Same action repeated {self.max_exact_repeats} times"

        if len(self._history) >= 4:
            history = list(self._history)

            for cycle_len in range(2, min(self.max_cycle_length + 1, len(history) // 2 + 1)):
                recent = history[-cycle_len * 2 :]
                if recent[:cycle_len] == recent[cycle_len:]:
                    return f"Detected repeating cycle of length {cycle_len}"

        return None

    def clear(self) -> None:
        self._history.clear()
