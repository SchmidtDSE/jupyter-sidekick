"""A protocol-correct minimal ACP agent, for tests.

Run as a subprocess over stdio via ``acp.run_agent``. Implements just enough of
``acp.Agent`` to exercise our client + harness without a real harness binary or
any auth. Advertises models/modes/config at ``new_session`` and can be told to
emit reactive updates via sentinel prompts.

MUST NOT write to stdout except via the ACP transport — stdout is the protocol
channel.
"""
from __future__ import annotations

import asyncio

import acp
from acp import schema as S

# Advertised capabilities (imported by tests to assert against).
MODELS = [("sonnet", "Claude Sonnet"), ("opus", "Claude Opus")]
CURRENT_MODEL = "sonnet"
MODES = [("default", "Default"), ("plan", "Plan")]
CURRENT_MODE = "default"
CONFIG_BOOL = ("verbose", "Verbose", False)  # id, name, current_value


def _model_state():
    return S.SessionModelState(
        availableModels=[S.ModelInfo(modelId=mid, name=name) for mid, name in MODELS],
        currentModelId=CURRENT_MODEL,
    )


def _mode_state():
    return S.SessionModeState(
        availableModes=[S.SessionMode(id=mid, name=name) for mid, name in MODES],
        currentModeId=CURRENT_MODE,
    )


def _config_options(value=None):
    cid, cname, cval = CONFIG_BOOL
    return [
        S.SessionConfigOptionBoolean(
            id=cid, name=cname, type="boolean",
            currentValue=cval if value is None else value,
        )
    ]


class FakeAgent(acp.Agent):
    def __init__(self) -> None:
        self._conn = None

    def on_connect(self, conn) -> None:
        self._conn = conn

    async def initialize(self, protocol_version, client_capabilities=None, client_info=None, **kwargs):
        return acp.InitializeResponse(protocolVersion=acp.PROTOCOL_VERSION)

    async def new_session(self, cwd, mcp_servers=None, **kwargs):
        return acp.NewSessionResponse(
            sessionId="fake-session-1",
            models=_model_state(),
            modes=_mode_state(),
            configOptions=_config_options(),
        )

    async def load_session(self, cwd, session_id, mcp_servers=None, **kwargs):
        # Replay a tiny prior conversation so resume tests can observe it, then
        # return the same capability payload new_session advertises.
        await self._conn.session_update(
            session_id=session_id,
            update=S.UserMessageChunk(
                content=acp.text_block("prior question"),
                sessionUpdate="user_message_chunk",
            ),
        )
        await self._conn.session_update(
            session_id=session_id,
            update=acp.update_agent_message_text("prior answer"),
        )
        return acp.LoadSessionResponse(
            models=_model_state(), modes=_mode_state(), configOptions=_config_options()
        )

    async def set_session_model(self, model_id, session_id, **kwargs):
        return None

    async def set_session_mode(self, mode_id, session_id, **kwargs):
        return None

    async def set_config_option(self, config_id, session_id, value, **kwargs):
        return None

    async def prompt(self, prompt, session_id, message_id=None, **kwargs):
        incoming = "".join(getattr(block, "text", "") for block in prompt)
        if incoming.startswith("EMIT_MODE="):
            mode = incoming.split("=", 1)[1]
            await self._conn.session_update(
                session_id=session_id,
                update=S.CurrentModeUpdate(
                    currentModeId=mode, sessionUpdate="current_mode_update"
                ),
            )
        elif incoming.startswith("EMIT_TOOL"):
            # A reasoning chunk, then a tool call that goes pending -> completed.
            await self._conn.session_update(
                session_id=session_id,
                update=acp.update_agent_thought_text("thinking it over"),
            )
            await self._conn.session_update(
                session_id=session_id,
                update=acp.update_tool_call(
                    tool_call_id="tc1",
                    title="Run tests",
                    kind="execute",
                    status="pending",
                    content=[
                        S.FileEditToolCallContent(
                            type="diff", path="/x.py", oldText="a\nb", newText="a\nc"
                        ),
                        S.ContentToolCallContent(
                            type="content", content=acp.text_block("ran 3 tests")
                        ),
                    ],
                    locations=[S.ToolCallLocation(path="/x.py", line=12)],
                ),
            )
            await self._conn.session_update(
                session_id=session_id,
                update=acp.update_tool_call(tool_call_id="tc1", status="completed"),
            )
            await self._conn.session_update(
                session_id=session_id,
                update=acp.update_agent_message_text("done"),
            )
        elif incoming.startswith("EMIT_CONFIG="):
            cid, val = incoming.split("=", 1)[1].split(":", 1)
            await self._conn.session_update(
                session_id=session_id,
                update=S.ConfigOptionUpdate(
                    configOptions=[
                        S.SessionConfigOptionBoolean(
                            id=cid, name=cid, type="boolean",
                            currentValue=(val.lower() == "true"),
                        )
                    ],
                    sessionUpdate="config_option_update",
                ),
            )
        else:
            await self._conn.session_update(
                session_id=session_id,
                update=acp.update_agent_message_text(f"echo: {incoming}"),
            )
        return acp.PromptResponse(stopReason="end_turn")


if __name__ == "__main__":
    asyncio.run(acp.run_agent(FakeAgent(), use_unstable_protocol=True))
