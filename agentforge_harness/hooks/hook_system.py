import asyncio
import json
import logging
import os
import signal
import sys
import tempfile
from typing import Any
from agentforge_harness.config.config import Config, HookConfig, HookTrigger
from agentforge_harness.tools.base import ToolResult

logger = logging.getLogger(__name__)


class HookSystem:
    def __init__(self, config: Config):
        self.config = config
        self.hooks: list[HookConfig] = []
        if self.config.hooks_enabled:
            self.hooks = [hook for hook in self.config.hooks if hook.enabled]

    async def _run_hook(self, hook: HookConfig, env: dict[str, str]) -> None:
        try:
            if hook.command:
                await self._run_command(hook.command, hook.timeout_sec, env)
            else:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".sh", delete=False
                ) as f:
                    f.write("#!/bin/bash\n")
                    f.write(hook.script)
                    script_path = f.name
                try:
                    os.chmod(script_path, 0o755)
                    await self._run_command(script_path, hook.timeout_sec, env)
                finally:
                    os.unlink(script_path)
        except Exception as e:
            logger.warning("Hook '%s' failed: %s", hook.name, e)
            if hook.fail_closed:
                raise

    async def _run_command(
        self,
        command: str,
        timeout: float,
        env: dict[str, str],
    ) -> None:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.config.cwd,
            env=env,
            start_new_session=True,
        )

        try:
            await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            if sys.platform != "win32":
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            else:
                process.kill()
            await process.wait()

    def _build_env(
        self,
        trigger: HookTrigger,
        tool_name: str | None = None,
        user_message: str | None = None,
        error: Exception | None = None,
    ) -> dict[str, str]:
        env = os.environ.copy()
        env["AGENTFORGE_TRIGGER"] = trigger.value
        env["AGENTFORGE_CWD"] = str(self.config.cwd)

        if tool_name:
            env["AGENTFORGE_TOOL_NAME"] = tool_name

        if user_message:
            env["AGENTFORGE_USER_MESSAGE"] = user_message

        if error:
            env["AGENTFORGE_ERROR"] = str(error)

        return env

    async def trigger_before_agent(self, user_message: str) -> None:
        env = self._build_env(
            HookTrigger.BEFORE_AGENT,
            user_message=user_message,
        )

        for hook in self.hooks:
            if hook.trigger == HookTrigger.BEFORE_AGENT:
                await self._run_hook(hook, env)

    async def trigger_after_agent(
        self,
        user_message: str,
        agent_response: str,
    ) -> None:
        env = self._build_env(
            HookTrigger.AFTER_AGENT,
            user_message=user_message,
        )
        env["AGENTFORGE_RESPONSE"] = agent_response

        for hook in self.hooks:
            if hook.trigger == HookTrigger.AFTER_AGENT:
                await self._run_hook(hook, env)

    async def trigger_before_tool(
        self,
        tool_name: str,
        tool_params: dict[str, Any],
    ) -> None:
        env = self._build_env(HookTrigger.BEFORE_TOOL, tool_name=tool_name)
        env["AGENTFORGE_TOOL_PARAMS"] = json.dumps(tool_params)

        for hook in self.hooks:
            if hook.trigger == HookTrigger.BEFORE_TOOL:
                await self._run_hook(hook, env)

    async def trigger_after_tool(
        self,
        tool_name: str,
        tool_params: dict[str, Any],
        tool_result: ToolResult,
    ) -> None:
        env = self._build_env(HookTrigger.AFTER_TOOL, tool_name=tool_name)
        env["AGENTFORGE_TOOL_PARAMS"] = json.dumps(tool_params)
        env["AGENTFORGE_TOOL_RESULT"] = tool_result.to_model_output()

        for hook in self.hooks:
            if hook.trigger == HookTrigger.AFTER_TOOL:
                await self._run_hook(hook, env)

    async def trigger_on_error(self, error: Exception) -> None:
        env = self._build_env(HookTrigger.ON_ERROR, error=error)

        for hook in self.hooks:
            if hook.trigger == HookTrigger.ON_ERROR:
                await self._run_hook(hook, env)
