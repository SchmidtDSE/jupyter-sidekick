"""Serialize ACP `session/update` objects into JSON-able dicts for the browser.

Each update's `session_update` discriminator is used as a uniform ``type`` tag,
enriched with type-specific fields for the kinds the UI renders today. Unknown
kinds fall back to the type tag alone (never crash). Tool-call rendering is a
follow-up.
"""
from __future__ import annotations

from typing import Any, Dict

from acp import schema as S

from .state import SessionState


def _block_text(content) -> str:
    return getattr(content, "text", "") or ""


def update_to_json(update) -> Dict[str, Any]:
    kind = getattr(update, "session_update", None)
    if isinstance(update, S.AgentMessageChunk):
        return {"type": kind, "text": _block_text(update.content)}
    if isinstance(update, S.AgentThoughtChunk):
        return {"type": kind, "text": _block_text(update.content)}
    if isinstance(update, S.UserMessageChunk):
        # Emitted when replaying a resumed session, so prior user turns render.
        return {"type": kind, "text": _block_text(update.content)}
    if isinstance(update, S.CurrentModeUpdate):
        return {"type": kind, "mode_id": update.current_mode_id}
    if isinstance(update, S.ConfigOptionUpdate):
        return {"type": kind, "config_options": SessionState._map_config(update.config_options)}
    if isinstance(update, S.AvailableCommandsUpdate):
        return {
            "type": kind,
            "commands": [
                {"name": c.name, "description": getattr(c, "description", None)}
                for c in (update.available_commands or [])
            ],
        }
    return {"type": kind}
