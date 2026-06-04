"""Registry of bindable ACP harnesses.

A `HarnessSpec` is the static launch metadata for one agent (how to spawn it).
It carries no model lists, modes, or config — everything dynamic is queried from
the live ACP session (see `SessionState`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Mapping, Optional, Tuple


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
