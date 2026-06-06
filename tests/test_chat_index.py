"""ChatIndex: the per-server JSON store backing chat history / resume."""
from __future__ import annotations

import json
import os

from jupyterlab_acp import chat_index as ci_mod
from jupyterlab_acp.chat_index import ChatIndex


def _ticking_clock(monkeypatch, start=1000.0):
    """Make time.time() return a strictly-increasing value per call, so
    created_at/updated_at ordering is deterministic without time-only args."""
    state = {"t": start}

    def tick():
        state["t"] += 1
        return state["t"]

    monkeypatch.setattr(ci_mod.time, "time", tick)


def test_record_creates_and_persists(tmp_path, monkeypatch):
    _ticking_clock(monkeypatch)
    path = str(tmp_path / "chats.json")
    index = ChatIndex(path)
    rec = index.record("c1", "claude-code", "sess-1", "/work")
    assert rec["chat_id"] == "c1"
    assert rec["harness_id"] == "claude-code"
    assert rec["session_id"] == "sess-1"
    assert rec["cwd"] == "/work"
    assert rec["title"] is None
    # Persisted to disk and reloaded by a fresh instance.
    assert os.path.exists(path)
    assert ChatIndex(path).get("c1")["session_id"] == "sess-1"


def test_record_again_refreshes_but_keeps_created_at(tmp_path, monkeypatch):
    _ticking_clock(monkeypatch)
    index = ChatIndex(str(tmp_path / "chats.json"))
    first = index.record("c1", "claude-code", "sess-1", "/work")
    created = first["created_at"]
    again = index.record("c1", "claude-code", "sess-2", "/work2")
    assert again["created_at"] == created  # unchanged
    assert again["session_id"] == "sess-2"  # refreshed
    assert again["updated_at"] > created


def test_set_title_only_once(tmp_path, monkeypatch):
    _ticking_clock(monkeypatch)
    index = ChatIndex(str(tmp_path / "chats.json"))
    index.record("c1", "claude-code", "sess-1", "/work")
    index.set_title("c1", "first message")
    index.set_title("c1", "second message")  # ignored
    assert index.get("c1")["title"] == "first message"
    index.set_title("absent", "noop")  # unknown chat is a no-op


def test_list_is_most_recent_first(tmp_path, monkeypatch):
    _ticking_clock(monkeypatch)
    index = ChatIndex(str(tmp_path / "chats.json"))
    index.record("c1", "a", "s1", "/w")
    index.record("c2", "a", "s2", "/w")
    index.record("c1", "a", "s1b", "/w")  # touches c1 last -> most recent
    listed = [r["chat_id"] for r in index.list()]
    assert listed == ["c1", "c2"]


def test_corrupt_file_starts_empty(tmp_path):
    path = tmp_path / "chats.json"
    path.write_text("{not json")
    assert ChatIndex(str(path)).list() == []


def test_missing_file_starts_empty(tmp_path):
    assert ChatIndex(str(tmp_path / "nope.json")).list() == []
