"""Registry of bindable ACP harnesses.

A `HarnessSpec` is the static launch metadata for one agent (how to spawn it).
It carries no model lists, modes, or config — everything dynamic is queried from
the live ACP session (see `SessionState`).
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple


class HarnessNotFoundError(KeyError):
    pass


@dataclass
class HarnessSpec:
    id: str
    display_name: str
    command: str
    args: Tuple[str, ...] = ()
    env: Optional[Mapping[str, str]] = None


class HarnessRegistry:
    def __init__(self) -> None:
        self._specs: "dict[str, HarnessSpec]" = {}

    def register(self, spec: HarnessSpec) -> None:
        if spec.id in self._specs:
            raise ValueError(f"Harness {spec.id!r} already registered")
        self._specs[spec.id] = spec

    def get(self, harness_id: str) -> HarnessSpec:
        try:
            return self._specs[harness_id]
        except KeyError as exc:
            raise HarnessNotFoundError(harness_id) from exc

    def list(self) -> List[HarnessSpec]:
        return list(self._specs.values())


def harness_listing(
    registry: HarnessRegistry,
    which: Callable[[str], Optional[str]] = shutil.which,
) -> List[Dict[str, Any]]:
    """Serialize the registry for the picker, marking which agents are actually
    installed (their command resolves on PATH) so the UI can disable the rest
    instead of letting a bind fail."""
    return [
        {
            "id": spec.id,
            "display_name": spec.display_name,
            "available": which(spec.command) is not None,
        }
        for spec in registry.list()
    ]
