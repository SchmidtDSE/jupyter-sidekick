"""SessionState: available-commands capture (for slash-command completion)."""
from __future__ import annotations

from acp import schema as S

from jupyter_acp.state import SessionState


def test_snapshot_has_empty_commands_by_default():
    assert SessionState().snapshot()["available_commands"] == []


def test_available_commands_update_populates_snapshot():
    state = SessionState()
    update = S.AvailableCommandsUpdate(
        availableCommands=[S.AvailableCommand(name="help", description="Show help")],
        sessionUpdate="available_commands_update",
    )
    assert state.apply_update(update) is True
    assert state.snapshot()["available_commands"] == [
        {"name": "help", "description": "Show help"}
    ]
