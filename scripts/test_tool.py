#!/usr/bin/env python3

import os
import sys
import json
from datetime import datetime


def main():
    trigger = os.environ.get("AGENTFORGE_TRIGGER")
    cwd = os.environ.get("AGENTFORGE_CWD")
    tool_name = os.environ.get("AGENTFORGE_TOOL_NAME")
    user_message = os.environ.get("AGENTFORGE_USER_MESSAGE")
    error = os.environ.get("AGENTFORGE_ERROR")

    log_data = {
        "timestamp": datetime.now().isoformat(),
        "trigger": trigger,
        "cwd": cwd,
        "tool_name": tool_name,
        "user_message": user_message,
        "error": error,
    }

    log_path = os.path.join(cwd or os.getcwd(), "hook.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a") as f:
        f.write(f"[HOOK] {json.dumps(log_data)}\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
