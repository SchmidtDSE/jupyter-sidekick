"""Process-wide map of chat_id -> ChatBinding, plus the bind operation.

`bind` is the end-to-end "open a bound chat": look up the harness spec, launch
its subprocess, open an ACP session, and record the (immutable) binding.
"""
from __future__ import annotations

from typing import Dict, Optional

from .binding import AlreadyBoundError, ChatBinding
from .harness import HarnessSession
from .registry import HarnessRegistry


class BindingManager:
    def __init__(self, registry: HarnessRegistry) -> None:
        self.registry = registry
        self._bindings: Dict[str, ChatBinding] = {}

    def get_or_create(self, chat_id: str) -> ChatBinding:
        if chat_id not in self._bindings:
            self._bindings[chat_id] = ChatBinding(chat_id)
        return self._bindings[chat_id]

    def lookup(self, chat_id: str) -> Optional[ChatBinding]:
        return self._bindings.get(chat_id)

    async def bind(
        self, chat_id: str, harness_id: str, cwd: Optional[str] = None
    ) -> ChatBinding:
        binding = self.get_or_create(chat_id)
        if binding.is_bound:
            raise AlreadyBoundError(
                f"chat {chat_id} already bound to {binding.harness_id!r}"
            )
        spec = self.registry.get(harness_id)  # raises HarnessNotFoundError
        return await self.bind_spec(chat_id, spec, cwd=cwd)

    async def bind_spec(self, chat_id, spec, cwd: Optional[str] = None) -> ChatBinding:
        """Bind a chat to an explicit HarnessSpec (e.g. one derived from the
        shared ACP registry), bypassing the local registry lookup."""
        binding = self.get_or_create(chat_id)
        if binding.is_bound:
            raise AlreadyBoundError(
                f"chat {chat_id} already bound to {binding.harness_id!r}"
            )
        session = HarnessSession(spec.command, *spec.args, cwd=cwd, env=spec.env)
        await session.start()
        await session.new_session(cwd=cwd)
        binding.bind(spec.id, session)
        return binding

    async def bind_for_resume(
        self, chat_id, spec, session_id: str, cwd: Optional[str] = None
    ) -> ChatBinding:
        """Bind a chat to a prior ACP session. Spawns + initializes the harness
        but defers `load_session` (recorded as `pending_resume`) so the stream
        handler can run it once a listener is attached and relay the replay."""
        binding = self.get_or_create(chat_id)
        if binding.is_bound:
            raise AlreadyBoundError(
                f"chat {chat_id} already bound to {binding.harness_id!r}"
            )
        session = HarnessSession(spec.command, *spec.args, cwd=cwd, env=spec.env)
        await session.start()
        binding.bind(spec.id, session)
        binding.pending_resume = (session_id, cwd or ".")
        return binding

    async def close(self, chat_id: str) -> None:
        binding = self._bindings.pop(chat_id, None)
        if binding is not None and binding.is_bound:
            await binding.session.close()

    async def close_all(self) -> None:
        for chat_id in list(self._bindings):
            await self.close(chat_id)
