"""The harness registry the server extension wires up (incl. user config)."""
from __future__ import annotations

from jupyter_sidekick.extension import DEFAULT_HARNESSES, build_default_registry, build_registry


def test_default_registry_includes_claude_code():
    spec = build_default_registry().get("claude-code")
    assert spec.command == "claude-agent-acp"


def test_default_registry_includes_copilot_and_qwen():
    ids = [s.id for s in build_default_registry().list()]
    assert "github-copilot" in ids
    assert "qwen-code" in ids


def test_build_registry_adds_and_overrides_by_id():
    registry = build_registry(
        DEFAULT_HARNESSES
        + [
            {"id": "claude-code", "display_name": "Claude (custom)", "command": "my-claude"},
            {"id": "custom", "display_name": "Custom", "command": "foo", "args": ["bar"]},
        ]
    )
    # user entry overrides the built-in by id
    assert registry.get("claude-code").command == "my-claude"
    assert registry.get("claude-code").display_name == "Claude (custom)"
    # and adds a brand-new one
    custom = registry.get("custom")
    assert custom.command == "foo"
    assert custom.args == ("bar",)


def test_extension_points_reference_the_app_class():
    from jupyter_sidekick import _jupyter_server_extension_points
    from jupyter_sidekick.extension import AcpExtension

    point = _jupyter_server_extension_points()[0]
    assert point["module"] == "jupyter_sidekick.extension"
    assert point["app"] is AcpExtension  # the class, not a string
