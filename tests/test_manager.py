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
