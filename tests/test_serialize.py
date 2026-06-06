"""Serialize ACP session updates to JSON-able dicts for the browser."""
from __future__ import annotations

import acp
from acp import schema as S

from jupyterlab_acp.serialize import update_to_json


def test_agent_message_chunk():
    assert update_to_json(acp.update_agent_message_text("hi")) == {
        "type": "agent_message_chunk",
        "text": "hi",
    }


def test_agent_thought_chunk():
    assert update_to_json(acp.update_agent_thought_text("hmm")) == {
        "type": "agent_thought_chunk",
        "text": "hmm",
    }


def test_current_mode_update():
    update = S.CurrentModeUpdate(currentModeId="plan", sessionUpdate="current_mode_update")
    assert update_to_json(update) == {"type": "current_mode_update", "mode_id": "plan"}


def test_config_option_update():
    opt = S.SessionConfigOptionBoolean(id="verbose", name="Verbose", type="boolean", currentValue=True)
    update = S.ConfigOptionUpdate(configOptions=[opt], sessionUpdate="config_option_update")
    out = update_to_json(update)
    assert out["type"] == "config_option_update"
    assert out["config_options"] == [
        {"id": "verbose", "name": "Verbose", "kind": "boolean", "value": True}
    ]


def test_available_commands_update():
    cmd = S.AvailableCommand(name="help", description="Show help")
    update = S.AvailableCommandsUpdate(
        availableCommands=[cmd], sessionUpdate="available_commands_update"
    )
    out = update_to_json(update)
    assert out["type"] == "available_commands_update"
    assert out["commands"] == [{"name": "help", "description": "Show help"}]


def test_user_message_chunk_carries_text():
    # User chunks are replayed when resuming a session, so prior user turns render.
    out = update_to_json(acp.update_user_message_text("prior question"))
    assert out == {"type": "user_message_chunk", "text": "prior question"}


def test_unhandled_update_falls_back_to_type_tag():
    # Tool-call updates aren't specially handled yet; serializer still tags type.
    out = update_to_json(acp.update_tool_call(tool_call_id="t1", title="Run tests"))
    assert out == {"type": "tool_call_update"}
