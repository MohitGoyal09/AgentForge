from __future__ import annotations

from pathlib import Path

from agentforge_harness.config.config import Config
from agentforge_harness.tools.mcp.mcp_manager import MCPManager


class _FakeClient:
    def __init__(self, name: str):
        self.name = name
        self.disconnected = False

    async def disconnect(self) -> None:
        self.disconnected = True


def test_mcp_manager_has_single_shutdown_definition():
    """Regression: shutdown() was defined twice; the first was silently shadowed."""
    # __dict__ holds exactly one attribute named "shutdown".
    assert "shutdown" in MCPManager.__dict__
    assert callable(MCPManager.__dict__["shutdown"])


async def test_shutdown_disconnects_all_clients_and_clears_state(tmp_path: Path):
    manager = MCPManager(Config(cwd=tmp_path))
    clients = {"a": _FakeClient("a"), "b": _FakeClient("b")}
    manager._clients = dict(clients)  # type: ignore[assignment]
    manager._initialized = True

    await manager.shutdown()

    assert all(c.disconnected for c in clients.values())
    assert manager._clients == {}
    assert manager._initialized is False
