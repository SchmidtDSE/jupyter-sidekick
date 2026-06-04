"""Our side of an ACP connection to a harness.

`HarnessClient` is the `acp.Client` the harness talks back to: it receives
streaming session updates (agent messages, tool calls, plan/mode/config updates)
and — in later slices — permission, file, and terminal requests. For now it
just fans session updates out to registered listeners; the other `acp.Client`
callbacks fall through to the library defaults.
"""
from __future__ import annotations

from typing import Callable, List

import acp


class HarnessClient(acp.Client):
    def __init__(self) -> None:
        self._update_listeners: List[Callable[[str, object], None]] = []

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
