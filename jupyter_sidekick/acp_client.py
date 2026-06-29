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
import os
from typing import Any, Callable, Dict, List, Optional

import acp
from acp import schema as S


def _slice_text(content: str, line: Optional[int], limit: Optional[int]) -> str:
    """Apply ACP read_text_file windowing: ``line`` is a 1-based start line and
    ``limit`` a max line count. No window → the whole file."""
    if not line and not limit:
        return content
    lines = content.splitlines(keepends=True)
    start = (line - 1) if line else 0
    if start < 0:
        start = 0
    end = (start + limit) if limit else len(lines)
    return "".join(lines[start:end])


def _disk_read(path: str, line: Optional[int], limit: Optional[int]) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return _slice_text(fh.read(), line, limit)


def _disk_write(path: str, content: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


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
        # Same UI round-trip as permissions, for fs/read+write: the handler
        # (the websocket) forwards the op to the browser, which applies it to the
        # live document and replies. Absent a handler (headless), we hit disk.
        self._fs_handler: Optional[Callable[[str, dict], None]] = None
        self._pending_fs: Dict[str, "asyncio.Future"] = {}
        self._fs_counter = 0

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

    # --- file system (fs/read_text_file, fs/write_text_file) ---

    def set_fs_handler(self, handler: Callable[[str, dict], None]) -> None:
        """Register the UI handler, called as ``handler(request_id, payload)`` to
        forward a file op to the browser. The UI later calls `resolve_fs`."""
        self._fs_handler = handler

    def clear_fs_handler(self) -> None:
        self._fs_handler = None

    def resolve_fs(self, request_id: str, result: Optional[dict]) -> None:
        """Resolve a pending fs op. ``result`` is the browser's reply, or None to
        signal 'not handled by the UI' (caller then falls back to disk)."""
        future = self._pending_fs.pop(request_id, None)
        if future is not None and not future.done():
            future.set_result(result)

    async def _ask_ui(self, op: str, path: str, content: Optional[str] = None):
        """Round-trip a file op to the browser; None if no UI is attached."""
        if self._fs_handler is None:
            return None
        self._fs_counter += 1
        request_id = f"fs-{self._fs_counter}"
        future = asyncio.get_event_loop().create_future()
        self._pending_fs[request_id] = future
        self._fs_handler(request_id, {"op": op, "path": path, "content": content})
        return await future

    async def read_text_file(self, path, session_id, limit=None, line=None, **kwargs):
        # Prefer the live in-browser document (it may hold unsaved edits the
        # agent should see); fall back to disk when it isn't open / no UI.
        result = await self._ask_ui("read", path)
        if result and result.get("found"):
            content = _slice_text(result.get("content") or "", line, limit)
        else:
            content = _disk_read(path, line, limit)
        return S.ReadTextFileResponse(content=content)

    async def write_text_file(self, content, path, session_id, **kwargs):
        # Apply to the live open document if possible (no disk change → no
        # overwrite/revert prompt); otherwise write straight to disk.
        result = await self._ask_ui("write", path, content)
        if not (result and result.get("applied")):
            _disk_write(path, content)
        return S.WriteTextFileResponse()
