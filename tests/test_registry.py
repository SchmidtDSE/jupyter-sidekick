"""HarnessRegistry: id -> launch spec for the agents the user can bind."""
from __future__ import annotations

import pytest

from jupyter_acp_chat.registry import (
    HarnessNotFoundError,
    HarnessRegistry,
    HarnessSpec,
    harness_listing,
)


def _spec(id_: str = "fake") -> HarnessSpec:
    return HarnessSpec(id=id_, display_name=id_.title(), command="python", args=("-c", "pass"))


def test_register_and_get():
    registry = HarnessRegistry()
    spec = _spec()
    registry.register(spec)
    assert registry.get("fake") is spec


def test_get_missing_raises():
    with pytest.raises(HarnessNotFoundError):
        HarnessRegistry().get("nope")


def test_duplicate_register_raises():
    registry = HarnessRegistry()
    registry.register(_spec())
    with pytest.raises(ValueError):
        registry.register(_spec())


def test_list_preserves_registration_order():
    registry = HarnessRegistry()
    registry.register(_spec("a"))
    registry.register(_spec("b"))
    assert [s.id for s in registry.list()] == ["a", "b"]


def test_harness_listing_marks_availability():
    registry = HarnessRegistry()
    registry.register(HarnessSpec(id="a", display_name="A", command="aaa"))
    registry.register(HarnessSpec(id="b", display_name="B", command="bbb"))
    listing = harness_listing(registry, which=lambda cmd: "/bin/aaa" if cmd == "aaa" else None)
    assert listing == [
        {"id": "a", "display_name": "A", "available": True},
        {"id": "b", "display_name": "B", "available": False},
    ]
