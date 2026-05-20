import asyncio
import os
from pathlib import Path
import signal
import sys
from tools.base import Tool, ToolConfirmation, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field
import fnmatch

BLOCKED_COMMANDS = {
    "rm -rf /",
    "rm -rf ~",
    "rm -rf /*",
    "dd if=/dev/zero",
    "dd if=/dev/random",
    "mkfs",
    "fdisk",
    "parted",
    ":(){ :|:& };:",  # Fork bomb
    "chmod 777 /",
    "chmod -R 777",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "init 0",
    "init 6",
}


class ShellParams(BaseModel):
    command: str = Field(..., description="The shell command to execute")
    timeout: int = Field(
        120, ge=1, le=600, description="Timeout in seconds (default: 120)"
    )
    cwd: str | None = Field(None, description="Working directory for the command")


class ShellTool(Tool):
    name = "shell"
    kind = ToolKind.SHELL
    description = "Execute a shell command. Use this for running system commands, scripts and CLI tools."

    schema = ShellParams

    async def get_confirmation(
        self, invocation: ToolInvocation
    ) -> ToolConfirmation | None:
        params = ShellParams(**invocation.params)

        for blocked in BLOCKED_COMMANDS:
            if blocked in params.command:
                return ToolConfirmation(
                    tool_name=self.name,
                    params=invocation.params,
                    description=f"Execute (BLOCKED): {params.command}",
                    command=params.command,
                    is_dangerous=True,
                )

        return ToolConfirmation(
            tool_name=self.name,
            params=invocation.params,
            description=f"Execute: {params.command}",
            command=params.command,
            is_dangerous=False,
        )
    
    def _build_environment(self) -> dict[str , str]:
        env = os.environ.copy()

        shell_enviornment = self.config.shell_environment

        if not shell_enviornment.ignore_default_excludes:
            for pattern in shell_enviornment.exclude_patterns:
                keys_to_remove = [
                    k for k in env.keys() if fnmatch.fnmatch(k.upper() , pattern.upper())
                ]

                for k in keys_to_remove:
                    del env[k]
        
        if shell_enviornment.set_vars:
            env.update(shell_enviornment.set_vars)
    
        return env

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = ShellParams(**invocation.params)

        command = params.command.lower().strip()
        for blocked in BLOCKED_COMMANDS:
            if blocked in command:
                return ToolResult.error_result(
                    f"Command blocked for safety: {params.command}",
                    metadata={"blocked": True},
                )

        if params.cwd:
            cwd = Path(params.cwd)
            if not cwd.is_absolute():
                cwd = invocation.cwd / cwd
        else:
            cwd = invocation.cwd

        if not cwd.exists():
            return ToolResult.error_result(f"Working directory doesn't exist: {cwd}")

        env = self._build_environment()
        if sys.platform == "win32":
            shell_cmd = ["cmd.exe" , "/c" , params.command]
        else:
            shell_cmd = ["/bin/bash" , "-c" , params.command]
        
        process = await asyncio.create_subprocess_exec(
            *shell_cmd,
            stdout = asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd = cwd,
            env = env,
            start_new_session= True
        )
        
        try : 
           stdout_data , stderr_data = await asyncio.wait_for(
            process.communicate(),
            timeout=params.timeout
           )
        except asyncio.TimeoutError:
            if sys.platform != "win32":
                os.killpg(os.getpgid(process.id) , signal.SIGILL)
            else:
                process.kill()
            await process.wait()
            return ToolResult.error_result(f"Command timed out after {process.timeout}s")
        
        stdout = stdout_data.decode("utf-8" , errors='replace')
        stderr = stderr_data.decode("utf-8" , errors = "replace")
        exit_code = process.returncode

        output = ""
        if stdout.rstrip():
            output +=stdout.rstrip() 
        if stderr.strip():
            output +=  "\n--- stderr ---\n"
            output += stderr.rstrip()
        
        if exit_code != 0:
            output += f"\nExit code: {exit_code}"

        if len(output) > 100 * 1024:
            output = output[: 100 * 1024] + "\n... [output truncated]"

        return ToolResult(
            success=exit_code == 0,
            output=output,
            error=stderr if exit_code != 0 else None,
            exit_code=exit_code,
        )




    
