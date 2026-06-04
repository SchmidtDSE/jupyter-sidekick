"""HarnessClient tool-permission handling: auto-approve headless, or defer to a
registered handler (the websocket → user approval UI)."""
from __future__ import annotations

import asyncio

from acp import schema as S

from jupyter_acp.acp_client import HarnessClient


def _options():
    return [
        S.PermissionOption(optionId="a", name="Allow once", kind="allow_once"),
        S.PermissionOption(optionId="r", name="Reject", kind="reject_once"),
    ]


def _tool_call():
    return S.ToolCallUpdate(toolCallId="t1", title="Edit notebook")


async def test_auto_allows_when_no_handler():
    client = HarnessClient()
    resp = await client.request_permission(
        options=_options(), session_id="s", tool_call=_tool_call()
    )
    assert type(resp.outcome).__name__ == "AllowedOutcome"
    assert resp.outcome.option_id == "a"


async def test_defers_to_handler_and_resolves_selection():
    client = HarnessClient()
    seen = {}
    client.set_permission_handler(lambda rid, payload: seen.update(rid=rid, payload=payload))

    async def approve_later():
        for _ in range(100):
            if "rid" in seen:
                break
            await asyncio.sleep(0.005)
        client.resolve_permission(seen["rid"], "r")

    task = asyncio.ensure_future(approve_later())
    resp = await client.request_permission(
        options=_options(), session_id="s", tool_call=_tool_call()
    )
    await task
    assert resp.outcome.option_id == "r"
    assert seen["payload"]["tool_call"]["title"] == "Edit notebook"
    assert [o["option_id"] for o in seen["payload"]["options"]] == ["a", "r"]


async def test_denies_when_resolved_with_none():
    client = HarnessClient()
    client.set_permission_handler(lambda rid, payload: client.resolve_permission(rid, None))
    resp = await client.request_permission(
        options=_options(), session_id="s", tool_call=_tool_call()
    )
    assert type(resp.outcome).__name__ == "DeniedOutcome"
