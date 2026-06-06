"""SessionState: available-commands capture (for slash-command completion)."""
from __future__ import annotations

from acp import schema as S

from jupyterlab_acp.state import SessionState


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


def test_map_config_boolean_has_no_choices():
    [mapped] = SessionState._map_config(
        [S.SessionConfigOptionBoolean(id="verbose", name="Verbose", type="boolean", currentValue=True)]
    )
    assert mapped == {"id": "verbose", "name": "Verbose", "kind": "boolean", "value": True}


def test_map_config_select_captures_choices():
    option = S.SessionConfigOptionSelect(
        id="effort",
        name="Effort",
        type="select",
        currentValue="high",
        options=[
            S.SessionConfigSelectOption(value="low", name="Low"),
            S.SessionConfigSelectOption(value="high", name="High"),
        ],
    )
    [mapped] = SessionState._map_config([option])
    assert mapped["id"] == "effort"
    assert mapped["value"] == "high"
    # Choice id is the option's `value`; name is its label.
    assert mapped["options"] == [
        {"id": "low", "name": "Low"},
        {"id": "high", "name": "High"},
    ]


def test_map_config_select_flattens_groups():
    option = S.SessionConfigOptionSelect(
        id="model",
        name="Model",
        type="select",
        currentValue="a",
        options=[
            S.SessionConfigSelectGroup(
                group="g1",
                name="Group 1",
                options=[S.SessionConfigSelectOption(value="a", name="A")],
            ),
            S.SessionConfigSelectGroup(
                group="g2",
                name="Group 2",
                options=[S.SessionConfigSelectOption(value="b", name="B")],
            ),
        ],
    )
    [mapped] = SessionState._map_config([option])
    assert mapped["options"] == [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
