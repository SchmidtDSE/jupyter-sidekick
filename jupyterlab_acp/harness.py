"""A live binding to one ACP harness subprocess, for one chat.

`HarnessSession` wraps `acp.spawn_agent_process` and the session lifecycle:
launch the harness, `initialize`, open a session, and `prompt` it. One
`HarnessSession` corresponds to one bound chat — the per-chat single-agent model.
"""
from __future__ import annotations

import contextlib
from typing import Mapping, Optional

import acp

from .acp_client import HarnessClient
from .state import SessionState


class HarnessSession:
    def __init__(
        self,
        command: str,
        *args: str,
        cwd: Optional[str] = None,
        env: Optional[Mapping[str, str]] = None,
        client: Optional[HarnessClient] = None,
    ) -> None:
        self.command = command
        self.args = args
        self.cwd = cwd
        self.env = env
        self.client = client if client is not None else HarnessClient()
        self.session_state = SessionState()
        self.client.add_update_listener(self._on_update)
        self._stack: Optional[contextlib.AsyncExitStack] = None
        self.conn = None
        self.process = None
        self.session_id: Optional[str] = None

    def _on_update(self, session_id, update) -> None:
        self.session_state.apply_update(update)

    async def start(self) -> "HarnessSession":
        self._stack = contextlib.AsyncExitStack()
        # set_session_model/mode/config_option are unstable-protocol methods in
        # ACP 0.9; capability switching is core to us, so we opt in.
        self.conn, self.process = await self._stack.enter_async_context(
            acp.spawn_agent_process(
                self.client,
                self.command,
                *self.args,
                cwd=self.cwd,
                env=self.env,
                use_unstable_protocol=True,
            )
        )
        await self.conn.initialize(protocol_version=acp.PROTOCOL_VERSION)
        return self

    async def new_session(self, cwd: Optional[str] = None):
        response = await self.conn.new_session(cwd=cwd or self.cwd or ".")
        self.session_id = response.sessionId
        self.session_state.load_new_session(response)
        return response

    async def load_session(self, session_id: str, cwd: Optional[str] = None):
        """Resume a prior session by id. The agent replays the conversation as
        `session/update` notifications (so a listener must be attached first),
        and returns the same capability payload as `new_session`."""
        response = await self.conn.load_session(
            cwd=cwd or self.cwd or ".", session_id=session_id
        )
        self.session_id = session_id
        self.session_state.load_new_session(response)
        return response

    async def prompt(self, text: str):
        return await self.conn.prompt(
            prompt=[acp.text_block(text)], session_id=self.session_id
        )

    async def set_model(self, model_id: str):
        response = await self.conn.set_session_model(
            model_id=model_id, session_id=self.session_id
        )
        self.session_state.set_selected_model(model_id)
        return response

    async def set_mode(self, mode_id: str):
        response = await self.conn.set_session_mode(
            mode_id=mode_id, session_id=self.session_id
        )
        self.session_state.set_selected_mode(mode_id)
        return response

    async def set_config_option(self, config_id: str, value):
        response = await self.conn.set_config_option(
            config_id=config_id, session_id=self.session_id, value=value
        )
        self.session_state.set_config_value(config_id, value)
        return response

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
