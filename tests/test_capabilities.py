"""Slice 2: capability state — the snapshot the UI renders, capability setters,
and reactive (agent-pushed) mode/config updates."""
from __future__ import annotations

import asyncio
import os
import sys

from jupyter_sidekick.harness import HarnessSession
from tests.fake_agent import CONFIG_BOOL, CURRENT_MODE, CURRENT_MODEL, MODELS, MODES

FAKE_AGENT = os.path.join(os.path.dirname(__file__), "fake_agent.py")


async def _started() -> HarnessSession:
    harness = HarnessSession(sys.executable, FAKE_AGENT, cwd=os.path.dirname(__file__))
    await harness.start()
    await harness.new_session()
    return harness


async def test_snapshot_reflects_advertised_capabilities():
    harness = await _started()
    try:
        snap = harness.session_state.snapshot()
        assert snap["available_models"] == [{"id": i, "name": n} for i, n in MODELS]
        assert snap["selected_model_id"] == CURRENT_MODEL
        assert snap["available_modes"] == [{"id": i, "name": n} for i, n in MODES]
        assert snap["selected_mode_id"] == CURRENT_MODE
        assert CONFIG_BOOL[0] in [c["id"] for c in snap["config_options"]]
    finally:
        await harness.close()


async def test_setters_update_local_selection():
    harness = await _started()
    try:
        await harness.set_model("opus")
        assert harness.session_state.snapshot()["selected_model_id"] == "opus"
        await harness.set_mode("plan")
        assert harness.session_state.snapshot()["selected_mode_id"] == "plan"
    finally:
        await harness.close()


async def test_reactive_current_mode_update():
    harness = await _started()
    try:
        assert harness.session_state.snapshot()["selected_mode_id"] == CURRENT_MODE
        # The agent flips its own mode and pushes an update — no setter call here.
        await harness.prompt("EMIT_MODE=plan")
        for _ in range(40):
            if harness.session_state.snapshot()["selected_mode_id"] == "plan":
                break
            await asyncio.sleep(0.05)
        assert harness.session_state.snapshot()["selected_mode_id"] == "plan"
    finally:
        await harness.close()


async def test_reactive_config_option_update():
    harness = await _started()

    def verbose_value():
        for c in harness.session_state.snapshot()["config_options"]:
            if c["id"] == "verbose":
                return c["value"]
        return None

    try:
        await harness.prompt("EMIT_CONFIG=verbose:true")
        for _ in range(40):
            if verbose_value() is True:
                break
            await asyncio.sleep(0.05)
        assert verbose_value() is True
    finally:
        await harness.close()
