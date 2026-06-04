"""Jupyter Server extension entry point.

Wires the default harness registry + BindingManager into the server settings and
registers the REST routes. Thin glue — the testable seam is
`build_default_registry`.
"""
from __future__ import annotations

from jupyter_server.extension.application import ExtensionApp
from jupyter_server.utils import url_path_join

from .handlers import (
    BindHandler,
    ConfigOptionHandler,
    HarnessesHandler,
    ModeHandler,
    ModelHandler,
    StateHandler,
    StreamHandler,
)
from .manager import BindingManager
from .registry import HarnessRegistry, HarnessSpec

# Default bindable harnesses. Launch metadata only — capabilities come from the
# live ACP session. `claude-agent-acp` is the Claude Code ACP server; OpenCode's
# exact ACP invocation is TBD pending a real-harness smoke test.
DEFAULT_HARNESSES = [
    HarnessSpec(id="claude-code", display_name="Claude Code", command="claude-agent-acp"),
    HarnessSpec(id="opencode", display_name="OpenCode", command="opencode"),
]


def build_default_registry() -> HarnessRegistry:
    registry = HarnessRegistry()
    for spec in DEFAULT_HARNESSES:
        registry.register(spec)
    return registry


class AcpExtension(ExtensionApp):
    name = "jupyter_acp"

    def initialize_settings(self) -> None:
        registry = build_default_registry()
        self.settings["acp_registry"] = registry
        self.settings["acp_manager"] = BindingManager(registry)

    def initialize_handlers(self) -> None:
        deps = dict(
            registry=self.settings["acp_registry"],
            manager=self.settings["acp_manager"],
        )
        base = self.name
        self.handlers.extend(
            [
                (url_path_join(base, "harnesses"), HarnessesHandler, deps),
                (url_path_join(base, r"chats/(.+)/bind"), BindHandler, deps),
                (url_path_join(base, r"chats/(.+)/state"), StateHandler, deps),
                (url_path_join(base, r"chats/(.+)/model"), ModelHandler, deps),
                (url_path_join(base, r"chats/(.+)/mode"), ModeHandler, deps),
                (url_path_join(base, r"chats/(.+)/config-option"), ConfigOptionHandler, deps),
                (url_path_join(base, r"chats/(.+)/stream"), StreamHandler, deps),
            ]
        )
