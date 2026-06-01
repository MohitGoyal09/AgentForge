from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentforge_harness.agent.agent import Agent
from agentforge_harness.config.config import ApprovalPolicy, Config, HookConfig, HookTrigger
from agentforge_harness.hooks.hook_system import HookSystem
from agentforge_harness.safety.approval import ApprovalManager
from agentforge_harness.tools.base import FileDiff, ToolConfirmation, ToolResult
from agentforge_harness.utils.redaction import redact_tool_confirmation, redact_tool_params


FAKE_OPENAI_KEY = "sk-" + "a" * 32
FAKE_GITHUB_TOKEN = "ghp_" + "b" * 36


def test_redact_tool_params_recurses_through_arguments():
    params = {
        "command": f"echo {FAKE_OPENAI_KEY}",
        "nested": {"token": FAKE_GITHUB_TOKEN},
    }

    redacted, report = redact_tool_params(params)

    rendered = json.dumps(redacted)
    assert FAKE_OPENAI_KEY not in rendered
    assert FAKE_GITHUB_TOKEN not in rendered
    assert report.count == 2


def test_redact_tool_confirmation_redacts_command_description_params_and_diff(tmp_path: Path):
    confirmation = ToolConfirmation(
        tool_name="write_file",
        params={"content": f"API_KEY={FAKE_OPENAI_KEY}"},
        description=f"Write secret {FAKE_GITHUB_TOKEN}",
        command=f"echo {FAKE_OPENAI_KEY}",
        diff=FileDiff(
            path=tmp_path / "secret.txt",
            old_content="",
            new_content=f"TOKEN={FAKE_GITHUB_TOKEN}",
            is_new_file=True,
        ),
        diff_text=f"+SECRET={FAKE_OPENAI_KEY}",
    )

    redacted = redact_tool_confirmation(confirmation)

    rendered = json.dumps(redacted.params) + redacted.description + (redacted.command or "")
    assert FAKE_OPENAI_KEY not in rendered
    assert FAKE_GITHUB_TOKEN not in rendered
    assert FAKE_GITHUB_TOKEN not in redacted.get_diff_text()
    assert FAKE_OPENAI_KEY not in (redacted.diff_text or "")
    assert "redacted" in redacted.description


def test_approval_manager_sends_redacted_confirmation_to_callback(tmp_path: Path):
    seen: list[ToolConfirmation] = []

    def callback(confirmation: ToolConfirmation) -> bool:
        seen.append(confirmation)
        return True

    manager = ApprovalManager(
        ApprovalPolicy.ON_REQUEST,
        tmp_path,
        confirmation_callback=callback,
        redaction_enabled=True,
    )
    confirmation = ToolConfirmation(
        tool_name="shell",
        params={"command": f"echo {FAKE_OPENAI_KEY}"},
        description=f"Execute: echo {FAKE_OPENAI_KEY}",
        command=f"echo {FAKE_OPENAI_KEY}",
        is_dangerous=True,
    )

    assert manager.request_confirmation(confirmation) is True

    assert seen
    rendered = json.dumps(seen[0].params) + seen[0].description + (seen[0].command or "")
    assert FAKE_OPENAI_KEY not in rendered
    assert FAKE_OPENAI_KEY in json.dumps(confirmation.params)


async def test_hook_system_redacts_tool_params_in_env(tmp_path: Path):
    config = Config(
        cwd=tmp_path,
        hooks_enabled=True,
        hooks=[
            HookConfig(
                name="capture",
                trigger=HookTrigger.BEFORE_TOOL,
                command="true",
            )
        ],
    )

    class CapturingHookSystem(HookSystem):
        def __init__(self, config: Config):
            super().__init__(config)
            self.envs: list[dict[str, str]] = []

        async def _run_hook(self, hook: HookConfig, env: dict[str, str]) -> None:
            self.envs.append(env)

    hooks = CapturingHookSystem(config)

    await hooks.trigger_before_tool("shell", {"command": f"echo {FAKE_OPENAI_KEY}"})

    assert hooks.envs
    params = hooks.envs[0]["AGENTFORGE_TOOL_PARAMS"]
    assert FAKE_OPENAI_KEY not in params
    assert "[REDACTED:OPENAI_API_KEY]" in params


def test_agent_tool_call_event_arguments_are_redacted(tmp_path: Path):
    agent = Agent(Config(cwd=tmp_path))

    redacted = agent._display_tool_arguments({"command": f"echo {FAKE_OPENAI_KEY}"})

    assert FAKE_OPENAI_KEY not in json.dumps(redacted)
    assert "[REDACTED:OPENAI_API_KEY]" in json.dumps(redacted)


def test_agent_tool_call_event_arguments_can_skip_redaction(tmp_path: Path):
    agent = Agent(Config(cwd=tmp_path, redaction_enabled=False))

    display = agent._display_tool_arguments({"command": f"echo {FAKE_OPENAI_KEY}"})

    assert FAKE_OPENAI_KEY in json.dumps(display)
