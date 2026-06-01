from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path


def main() -> None:
    log_path = Path(os.environ.get("AGENTFORGE_HOOK_LOG", "agentforge-hook.log"))
    payload = {
        "timestamp": datetime.now().isoformat(),
        "trigger": os.environ.get("AGENTFORGE_HOOK_TRIGGER"),
        "tool": os.environ.get("AGENTFORGE_TOOL_NAME"),
        "success": os.environ.get("AGENTFORGE_TOOL_SUCCESS"),
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")


if __name__ == "__main__":
    main()
