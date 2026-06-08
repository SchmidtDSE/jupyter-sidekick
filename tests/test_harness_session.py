"""First vertical slice: launch a harness over ACP, open a session, prompt it,
and receive the streamed agent reply — exercised against a fake agent."""
from __future__ import annotations

import asyncio
import os
import sys

from jupyter_sidekick.acp_client import HarnessClient
from jupyter_sidekick.harness import HarnessSession

FAKE_AGENT = os.path.join(os.path.dirname(__file__), "fake_agent.py")


def _agent_message_text(update):
    content = getattr(update, "content", None)
    return getattr(content, "text", None) if content is not None else None


async def test_prompt_round_trip_with_fake_agent():
    received = []
    client = HarnessClient()
    client.add_update_listener(lambda session_id, update: received.append(update))

    harness = HarnessSession(
        sys.executable,
        FAKE_AGENT,
        cwd=os.path.dirname(__file__),
        client=client,
    )
    await harness.start()
    try:
        await harness.new_session()
        assert harness.session_id == "fake-session-1"

        response = await harness.prompt("hello")
        assert response.stopReason == "end_turn"

        # The agent streamed an agent-message chunk back to our client.
        for _ in range(40):
            if any(_agent_message_text(u) == "echo: hello" for u in received):
                break
            await asyncio.sleep(0.05)
        texts = [t for t in (_agent_message_text(u) for u in received) if t]
        assert "echo: hello" in texts
    finally:
        await harness.close()
