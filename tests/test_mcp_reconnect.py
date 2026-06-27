"""Tests for MCPClient.reconnect() with exponential backoff."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from agentforge_harness.tools.mcp.client import MCPClient, MCPServerStatus


def _make_client() -> MCPClient:
    config = MagicMock()
    config.command = "echo"
    config.args = []
    config.env = {}
    config.cwd = None
    config.url = None
    return MCPClient(name="test-server", config=config, cwd=None)


@pytest.mark.asyncio
async def test_reconnect_succeeds_on_nth_try():
    """connect() fails twice then succeeds — reconnect() should return True."""
    client = _make_client()
    call_count = 0

    async def flaky_connect():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("not yet")
        client.status = MCPServerStatus.CONNECTED

    with patch.object(client, "connect", side_effect=flaky_connect), \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await client.reconnect(max_attempts=3, base_delay=1.0)

    assert result is True
    assert call_count == 3
    # Two sleeps for the two failures before the success
    assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_reconnect_returns_false_when_all_attempts_fail():
    """connect() always raises — reconnect() returns False after max_attempts tries."""
    client = _make_client()
    call_count = 0

    async def always_fail():
        nonlocal call_count
        call_count += 1
        raise ConnectionError("always down")

    with patch.object(client, "connect", side_effect=always_fail), \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await client.reconnect(max_attempts=3, base_delay=1.0)

    assert result is False
    assert call_count == 3
    # Two sleeps: after attempt 1 and after attempt 2 (not after the last)
    assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_reconnect_exponential_backoff_delays():
    """Verify sleep is called with base_delay * 2**attempt for each retry."""
    client = _make_client()

    async def always_fail():
        raise ConnectionError("down")

    with patch.object(client, "connect", side_effect=always_fail), \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await client.reconnect(max_attempts=3, base_delay=2.0)

    # attempt 0 → sleep(2.0 * 2**0 = 2.0)
    # attempt 1 → sleep(2.0 * 2**1 = 4.0)
    # attempt 2 is last, no sleep after it
    assert mock_sleep.call_args_list == [call(2.0), call(4.0)]


@pytest.mark.asyncio
async def test_reconnect_resets_status_to_disconnected():
    """Status is reset to DISCONNECTED at the start of reconnect()."""
    client = _make_client()
    client.status = MCPServerStatus.ERROR
    statuses_at_entry: list[MCPServerStatus] = []

    async def capture_status():
        statuses_at_entry.append(client.status)
        raise ConnectionError("fail")

    with patch.object(client, "connect", side_effect=capture_status), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        await client.reconnect(max_attempts=1)

    assert statuses_at_entry[0] == MCPServerStatus.DISCONNECTED
