"""BindingManager: chat_id -> ChatBinding, and the bind operation that launches
a harness and opens its ACP session. Exercised against the fake agent."""
from __future__ import annotations

import os
import sys

import pytest

from jupyterlab_acp.binding import AlreadyBoundError
from jupyterlab_acp.manager import BindingManager
from jupyterlab_acp.registry import HarnessNotFoundError, HarnessRegistry, HarnessSpec

FAKE_AGENT = os.path.join(os.path.dirname(__file__), "fake_agent.py")
HERE = os.path.dirname(__file__)


def _registry() -> HarnessRegistry:
    registry = HarnessRegistry()
    registry.register(
        HarnessSpec(id="fake", display_name="Fake", command=sys.executable, args=(FAKE_AGENT,))
    )
    return registry


async def test_bind_starts_session_and_loads_capabilities():
    manager = BindingManager(_registry())
    binding = await manager.bind("chat-1", "fake", cwd=HERE)
    try:
        assert binding.is_bound
        assert binding.harness_id == "fake"
        assert binding.session.session_id == "fake-session-1"
        assert binding.session.session_state.snapshot()["selected_model_id"] == "sonnet"
    finally:
        await manager.close_all()


async def test_rebind_same_chat_raises():
    manager = BindingManager(_registry())
    await manager.bind("chat-1", "fake", cwd=HERE)
    try:
        with pytest.raises(AlreadyBoundError):
            await manager.bind("chat-1", "fake", cwd=HERE)
    finally:
        await manager.close_all()


async def test_bind_unknown_harness_raises():
    manager = BindingManager(_registry())
    with pytest.raises(HarnessNotFoundError):
        await manager.bind("chat-1", "nope")


async def test_lookup_returns_none_then_binding():
    manager = BindingManager(_registry())
    assert manager.lookup("absent") is None
    await manager.bind("chat-1", "fake", cwd=HERE)
    try:
        assert manager.lookup("chat-1").harness_id == "fake"
    finally:
        await manager.close_all()


async def test_close_tears_down_binding():
    manager = BindingManager(_registry())
    await manager.bind("chat-1", "fake", cwd=HERE)
    await manager.close("chat-1")
    # The binding is gone, so a fresh bind on the same chat_id is allowed (no
    # leftover subprocess, no AlreadyBoundError).
    assert manager.lookup("chat-1") is None
    rebind = await manager.bind("chat-1", "fake", cwd=HERE)
    try:
        assert rebind.is_bound
    finally:
        await manager.close_all()


async def test_close_absent_chat_is_noop():
    # Idempotent: closing an unknown/already-closed chat must not raise, so a
    # double-close (reset then dispose) is safe.
    manager = BindingManager(_registry())
    await manager.close("never-bound")


async def test_prompt_streams_thought_and_tool_call_updates():
    import asyncio

    from jupyterlab_acp.serialize import update_to_json

    manager = BindingManager(_registry())
    binding = await manager.bind("chat-1", "fake", cwd=HERE)
    seen = []
    binding.session.client.add_update_listener(lambda sid, u: seen.append(update_to_json(u)))
    try:
        await binding.session.prompt("EMIT_TOOL")
        await asyncio.sleep(0.3)  # let trailing notifications drain
    finally:
        await manager.close_all()
    assert seen == [
        {"type": "agent_thought_chunk", "text": "thinking it over"},
        {
            "type": "tool_call_update",
            "tool_call_id": "tc1",
            "title": "Run tests",
            "kind": "execute",
            "status": "pending",
            "content": [
                {"block": "diff", "path": "/x.py", "old_text": "a\nb", "new_text": "a\nc"},
                {"block": "content", "text": "ran 3 tests"},
            ],
            "locations": [{"path": "/x.py", "line": 12}],
        },
        {"type": "tool_call_update", "tool_call_id": "tc1", "status": "completed"},
        {"type": "agent_message_chunk", "text": "done"},
    ]


async def test_bind_for_resume_defers_load_then_reloads():
    manager = BindingManager(_registry())
    spec = manager.registry.get("fake")
    binding = await manager.bind_for_resume("chat-1", spec, "fake-session-1", HERE)
    try:
        # Bound, but the load is deferred until the stream attaches.
        assert binding.is_bound
        assert binding.pending_resume == ("fake-session-1", HERE)
        assert binding.session.session_id is None
        # Running the deferred load reloads the session + capabilities.
        await binding.session.load_session(*binding.pending_resume)
        assert binding.session.session_id == "fake-session-1"
        assert binding.session.session_state.snapshot()["selected_model_id"] == "sonnet"
    finally:
        await manager.close_all()
