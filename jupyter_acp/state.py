"""Capability state for one ACP session.

`SessionState` is the snapshot the UI renders: available models / modes / config
options and the current selections. It is seeded from the `new_session` response
and kept current both by our own capability setters (optimistic local tracking,
since ACP has no reactive *model* update) and by reactive updates the harness
pushes (`CurrentModeUpdate`, `ConfigOptionUpdate`).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from acp import schema as S


class SessionState:
    def __init__(self) -> None:
        self.available_models: List[Dict[str, Any]] = []
        self.selected_model_id: Optional[str] = None
        self.available_modes: List[Dict[str, Any]] = []
        self.selected_mode_id: Optional[str] = None
        self.config_options: List[Dict[str, Any]] = []

    def load_new_session(self, response) -> None:
        models = getattr(response, "models", None)
        if models is not None:
            self.available_models = [
                {"id": m.model_id, "name": m.name}
                for m in (models.available_models or [])
            ]
            self.selected_model_id = models.current_model_id
        modes = getattr(response, "modes", None)
        if modes is not None:
            self.available_modes = [
                {"id": m.id, "name": m.name} for m in (modes.available_modes or [])
            ]
            self.selected_mode_id = modes.current_mode_id
        config = getattr(response, "config_options", None)
        if config is not None:
            self.config_options = self._map_config(config)

    def apply_update(self, update) -> bool:
        """Apply a reactive `session/update`. Returns True if it changed state."""
        if isinstance(update, S.CurrentModeUpdate):
            self.selected_mode_id = update.current_mode_id
            return True
        if isinstance(update, S.ConfigOptionUpdate):
            self.config_options = self._map_config(update.config_options)
            return True
        return False

    def set_selected_model(self, model_id: str) -> None:
        self.selected_model_id = model_id

    def set_selected_mode(self, mode_id: str) -> None:
        self.selected_mode_id = mode_id

    def set_config_value(self, config_id: str, value: Any) -> None:
        for option in self.config_options:
            if option.get("id") == config_id:
                option["value"] = value

    def snapshot(self) -> Dict[str, Any]:
        return {
            "available_models": [dict(m) for m in self.available_models],
            "selected_model_id": self.selected_model_id,
            "available_modes": [dict(m) for m in self.available_modes],
            "selected_mode_id": self.selected_mode_id,
            "config_options": [dict(c) for c in self.config_options],
        }

    @staticmethod
    def _map_config(options) -> List[Dict[str, Any]]:
        mapped: List[Dict[str, Any]] = []
        for option in options or []:
            mapped.append(
                {
                    "id": option.id,
                    "name": option.name,
                    "kind": getattr(option, "type", None),
                    "value": getattr(option, "current_value", None),
                }
            )
        return mapped
