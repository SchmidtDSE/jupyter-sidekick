"""Per-chat binding state.

A `ChatBinding` is draft until a harness is bound, then immutable — the per-chat
single-agent invariant. Switching harness means a new chat, not a rebind.
"""
from __future__ import annotations

from typing import Optional


class AlreadyBoundError(RuntimeError):
    pass


class NotBoundError(RuntimeError):
    pass


class ChatBinding:
    def __init__(self, chat_id: str) -> None:
        self.chat_id = chat_id
        self._harness_id: Optional[str] = None
        self._session = None
        # For a resumed chat: (session_id, cwd) to load once the stream attaches,
        # so the agent's replay reaches the browser. Cleared after the load runs.
        self.pending_resume: Optional[tuple] = None

    @property
    def is_draft(self) -> bool:
        return self._harness_id is None

    @property
    def is_bound(self) -> bool:
        return self._harness_id is not None

    @property
    def harness_id(self) -> Optional[str]:
        return self._harness_id

    @property
    def session(self):
        if self._session is None:
            raise NotBoundError(f"chat {self.chat_id} has no harness bound")
        return self._session

    def bind(self, harness_id: str, session) -> None:
        if self._harness_id is not None:
            raise AlreadyBoundError(
                f"chat {self.chat_id} already bound to {self._harness_id!r}"
            )
        self._harness_id = harness_id
        self._session = session
