"""Jupyter Server extension entry point.

Wires the harness registry + BindingManager into the server settings and
registers the routes. Harnesses are launch metadata only — no per-harness code,
because every binding is just "a command that speaks ACP". Built-in defaults can
be extended or overridden from `jupyter_server_config` via the `harnesses`
config trait (Zed/JetBrains-style), e.g.:

    c.AcpExtension.harnesses = [
        {"id": "my-agent", "display_name": "My Agent",
         "command": "my-agent", "args": ["--acp"], "env": {"FOO": "bar"}},
    ]

The testable seam is `build_registry`.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List as ListT

from jupyter_server.extension.application import ExtensionApp
from jupyter_server.utils import url_path_join
from traitlets import Dict as DictTrait
from traitlets import List as ListTrait

from .acp_registry import AcpRegistry
from .chat_index import ChatIndex
from .handlers import (
    BindHandler,
    ChatsHandler,
    CloseHandler,
    ConfigOptionHandler,
    HarnessesHandler,
    ModeHandler,
    ModelHandler,
    RegistryHandler,
    ResumeHandler,
    StateHandler,
    StreamHandler,
)
from .manager import BindingManager
from .registry import HarnessRegistry, HarnessSpec

# Built-in harnesses. Each is launch metadata only; capabilities come from the
# live ACP session. Listed agents need their CLI installed + authed to bind.
# Commands per the ACP ecosystem (agentclientprotocol.com, Zed, JetBrains).
DEFAULT_HARNESSES: ListT[Dict[str, Any]] = [
    {"id": "claude-code", "display_name": "Claude Code", "command": "claude-agent-acp"},
    {"id": "opencode", "display_name": "OpenCode", "command": "opencode", "args": ["acp"]},
    {"id": "goose", "display_name": "Goose", "command": "goose", "args": ["acp"]},
    {"id": "github-copilot", "display_name": "GitHub Copilot", "command": "copilot", "args": ["--acp"]},
    {"id": "qwen-code", "display_name": "Qwen Code", "command": "qwen", "args": ["--experimental-acp"]},
    {"id": "gemini", "display_name": "Gemini CLI", "command": "gemini", "args": ["--experimental-acp"]},
]


def _spec_from_dict(spec: Dict[str, Any]) -> HarnessSpec:
    return HarnessSpec(
        id=spec["id"],
        display_name=spec.get("display_name", spec["id"]),
        command=spec["command"],
        args=tuple(spec.get("args", ())),
        env=spec.get("env"),
    )


def build_registry(specs: ListT[Dict[str, Any]]) -> HarnessRegistry:
    """Build a registry from spec dicts; later entries override earlier by id."""
    by_id: "dict[str, Dict[str, Any]]" = {}
    for spec in specs:
        by_id[spec["id"]] = spec
    registry = HarnessRegistry()
    for spec in by_id.values():
        registry.register(_spec_from_dict(spec))
    return registry


def build_default_registry() -> HarnessRegistry:
    return build_registry(DEFAULT_HARNESSES)


def default_chat_index_path() -> str:
    """Per-server JSON index location, under the Jupyter data dir."""
    from jupyter_core.paths import jupyter_data_dir

    return os.path.join(jupyter_data_dir(), "jupyterlab_acp", "chats.json")


class AcpExtension(ExtensionApp):
    name = "jupyterlab_acp"

    harnesses = ListTrait(
        DictTrait(),
        default_value=[],
        config=True,
        help="Extra ACP harnesses (or overrides of built-ins by id). Each is a "
        "dict with keys: id, display_name, command, args, env.",
    )

    def initialize_settings(self) -> None:
        registry = build_registry(DEFAULT_HARNESSES + list(self.harnesses))
        self.settings["acp_registry"] = registry
        self.settings["acp_manager"] = BindingManager(registry)
        self.settings["acp_remote_registry"] = AcpRegistry()
        self.settings["acp_chat_index"] = ChatIndex(default_chat_index_path())

    def initialize_handlers(self) -> None:
        base = self.name
        self.handlers.extend(
            [
                (url_path_join(base, "harnesses"), HarnessesHandler),
                (url_path_join(base, "registry"), RegistryHandler),
                (url_path_join(base, r"chats/(.+)/bind"), BindHandler),
                (url_path_join(base, r"chats/(.+)/state"), StateHandler),
                (url_path_join(base, r"chats/(.+)/model"), ModelHandler),
                (url_path_join(base, r"chats/(.+)/mode"), ModeHandler),
                (url_path_join(base, r"chats/(.+)/config-option"), ConfigOptionHandler),
                (url_path_join(base, r"chats/(.+)/close"), CloseHandler),
                (url_path_join(base, r"chats/(.+)/resume"), ResumeHandler),
                (url_path_join(base, "chats"), ChatsHandler),
                (url_path_join(base, r"chats/(.+)/stream"), StreamHandler),
            ]
        )

    async def stop_extension(self) -> None:
        # Backstop: tear down every live binding (and its harness subprocess) on
        # server shutdown, so nothing is orphaned even if clients never close.
        manager = self.settings.get("acp_manager")
        if manager is not None:
            await manager.close_all()
