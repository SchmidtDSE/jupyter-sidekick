"""HarnessClient listener management (needed so a websocket can detach cleanly)."""
from __future__ import annotations

from jupyter_acp_chat.acp_client import HarnessClient


async def test_listener_receives_then_stops_after_removal():
    client = HarnessClient()
    seen = []

    def listener(session_id, update):
        seen.append(update)

    client.add_update_listener(listener)
    await client.session_update("s1", "first")
    client.remove_update_listener(listener)
    await client.session_update("s1", "second")

    assert seen == ["first"]
