"""Our side of an ACP connection to a harness.

`HarnessClient` is the `acp.Client` the harness talks back to:
- it fans `session/update` notifications out to listeners (the websocket relays
  them to the browser), and
- it handles `session/request_permission` tool-approval requests, either
  auto-approving when no UI is attached (headless) or deferring to a registered
  handler (the websocket, which asks the user) and awaiting their choice.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Optional

import acp
from acp import schema as S


def _serialize_tool_call(tool_call) -> Dict[str, Any]:
    def coerce(v):
        return v if v is None or isinstance(v, (str, int, float, bool)) else str(v)

    return {
        "tool_call_id": getattr(tool_call, "tool_call_id", None),
        "title": getattr(tool_call, "title", None),
        "kind": coerce(getattr(tool_call, "kind", None)),
        "status": coerce(getattr(tool_call, "status", None)),
    }


class HarnessClient(acp.Client):
    def __init__(self) -> None:
        self._update_listeners: List[Callable[[str, object], None]] = []
        self._permission_handler: Optional[Callable[[str, dict], None]] = None
        self._pending_permissions: Dict[str, "asyncio.Future"] = {}
        self._permission_counter = 0

    # --- session updates ---

    def add_update_listener(self, callback: Callable[[str, object], None]) -> None:
        """Register a callback invoked as ``callback(session_id, update)`` for
        every ``session/update`` notification from the harness."""
        self._update_listeners.append(callback)

    def remove_update_listener(self, callback: Callable[[str, object], None]) -> None:
        """Detach a previously registered listener (e.g. on websocket close)."""
        try:
            self._update_listeners.remove(callback)
        except ValueError:
            pass

    async def session_update(self, session_id, update, **kwargs) -> None:
        for callback in list(self._update_listeners):
            callback(session_id, update)

    # --- tool permission ---

    def set_permission_handler(self, handler: Callable[[str, dict], None]) -> None:
        """Register the UI handler, called as ``handler(request_id, payload)`` to
        surface a permission request. The UI later calls `resolve_permission`."""
        self._permission_handler = handler

    def clear_permission_handler(self) -> None:
        self._permission_handler = None

    def resolve_permission(self, request_id: str, option_id: Optional[str]) -> None:
        """Resolve a pending request with the chosen option id (or None to deny)."""
        future = self._pending_permissions.pop(request_id, None)
        if future is not None and not future.done():
            future.set_result(option_id)

    async def request_permission(self, options, session_id, tool_call, **kwargs):
        if self._permission_handler is None:
            return self._auto_response(options)
        self._permission_counter += 1
        request_id = f"perm-{self._permission_counter}"
        future = asyncio.get_event_loop().create_future()
        self._pending_permissions[request_id] = future
        self._permission_handler(
            request_id,
            {
                "tool_call": _serialize_tool_call(tool_call),
                "options": [
                    {"option_id": o.option_id, "name": o.name, "kind": o.kind}
                    for o in options
                ],
            },
        )
        option_id = await future
        return self._response_for(option_id)

    @staticmethod
    def _response_for(option_id: Optional[str]):
        if option_id is None:
            return acp.RequestPermissionResponse(outcome=S.DeniedOutcome(outcome="cancelled"))
        return acp.RequestPermissionResponse(
            outcome=S.AllowedOutcome(optionId=option_id, outcome="selected")
        )

    @classmethod
    def _auto_response(cls, options):
        chosen = next((o.option_id for o in options if o.kind in ("allow_once", "allow_always")), None)
        if chosen is None and options:
            chosen = options[0].option_id
        return cls._response_for(chosen)
