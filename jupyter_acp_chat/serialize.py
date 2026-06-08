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


def _coerce(value):
    """Enum/literal values (kind, status) → plain JSON scalars."""
    return value if value is None or isinstance(value, (str, int, float, bool)) else str(value)


def _tool_content_block(item) -> Dict[str, Any] | None:
    """One ToolCall content entry → a JSON block the UI can render."""
    if isinstance(item, S.ContentToolCallContent):
        return {"block": "content", "text": _block_text(item.content)}
    if isinstance(item, S.FileEditToolCallContent):
        return {
            "block": "diff",
            "path": item.path,
            "old_text": item.old_text,
            "new_text": item.new_text,
        }
    if isinstance(item, S.TerminalToolCallContent):
        return {"block": "terminal", "terminal_id": item.terminal_id}
    return None


def _tool_call_json(type_tag: str, update) -> Dict[str, Any]:
    out: Dict[str, Any] = {"type": type_tag, "tool_call_id": update.tool_call_id}
    for field in ("title", "kind", "status"):
        value = getattr(update, field, None)
        if value is not None:
            out[field] = _coerce(value)
    content = getattr(update, "content", None)
    if content:
        blocks = [b for b in (_tool_content_block(c) for c in content) if b]
        if blocks:
            out["content"] = blocks
    locations = getattr(update, "locations", None)
    if locations:
        out["locations"] = [{"path": loc.path, "line": loc.line} for loc in locations]
    return out


def update_to_json(update) -> Dict[str, Any]:
    kind = getattr(update, "session_update", None)
    if isinstance(update, S.AgentMessageChunk):
        return {"type": kind, "text": _block_text(update.content)}
    if isinstance(update, S.AgentThoughtChunk):
        return {"type": kind, "text": _block_text(update.content)}
    if isinstance(update, S.UserMessageChunk):
        # Emitted when replaying a resumed session, so prior user turns render.
        return {"type": kind, "text": _block_text(update.content)}
    # tool_call (initial) and tool_call_update (partial) — the UI keys on
    # tool_call_id and merges later updates onto the first. Fields are optional
    # on an update, so absent ones are omitted. The initial ToolCall carries no
    # `sessionUpdate` discriminator, so the type tag is set explicitly per class.
    if isinstance(update, S.ToolCall):
        return _tool_call_json("tool_call", update)
    if isinstance(update, S.ToolCallProgress):
        return _tool_call_json("tool_call_update", update)
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
