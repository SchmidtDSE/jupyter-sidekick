"""HarnessClient file-system handling (fs/read_text_file, fs/write_text_file).

Headless (no handler) reads/writes hit disk directly. With a handler (the
websocket → live document in the browser), the op is forwarded and the disk is
left untouched when the UI applies it — the basis for live, in-notebook edits.
"""
from __future__ import annotations

import asyncio
import os

from jupyter_sidekick.acp_client import HarnessClient, _slice_text


def test_slice_text_windows_by_line_and_limit():
    body = "a\nb\nc\nd\n"
    assert _slice_text(body, None, None) == body
    assert _slice_text(body, 2, 2) == "b\nc\n"
    assert _slice_text(body, 3, None) == "c\nd\n"
    assert _slice_text(body, None, 2) == "a\nb\n"


async def test_headless_write_then_read_hits_disk(tmp_path):
    client = HarnessClient()
    path = str(tmp_path / "note.txt")

    await client.write_text_file(content="hello", path=path, session_id="s")
    assert os.path.exists(path)
    with open(path) as fh:
        assert fh.read() == "hello"

    resp = await client.read_text_file(path=path, session_id="s")
    assert resp.content == "hello"


async def test_ui_applied_write_does_not_touch_disk(tmp_path):
    client = HarnessClient()
    path = str(tmp_path / "open.txt")
    seen = []

    def handler(request_id, payload):
        seen.append(payload)
        client.resolve_fs(request_id, {"applied": True})

    client.set_fs_handler(handler)
    await client.write_text_file(content="live-edit", path=path, session_id="s")

    assert not os.path.exists(path), "UI applied the edit, so disk must be untouched"
    assert seen[0]["op"] == "write"
    assert seen[0]["content"] == "live-edit"


async def test_ui_not_applied_write_falls_back_to_disk(tmp_path):
    client = HarnessClient()
    path = str(tmp_path / "closed.txt")
    # File isn't open in the browser → handler reports not applied.
    client.set_fs_handler(lambda rid, payload: client.resolve_fs(rid, {"applied": False}))

    await client.write_text_file(content="on-disk", path=path, session_id="s")
    with open(path) as fh:
        assert fh.read() == "on-disk"


async def test_ui_read_prefers_live_content(tmp_path):
    client = HarnessClient()
    path = str(tmp_path / "live.txt")
    with open(path, "w") as fh:
        fh.write("STALE DISK")
    # The open document holds unsaved edits the agent should see, not disk.
    client.set_fs_handler(
        lambda rid, payload: client.resolve_fs(rid, {"found": True, "content": "FRESH LIVE"})
    )

    resp = await client.read_text_file(path=path, session_id="s")
    assert resp.content == "FRESH LIVE"


async def test_ui_read_not_found_falls_back_to_disk(tmp_path):
    client = HarnessClient()
    path = str(tmp_path / "ondisk.txt")
    with open(path, "w") as fh:
        fh.write("from disk")
    client.set_fs_handler(lambda rid, payload: client.resolve_fs(rid, {"found": False}))

    resp = await client.read_text_file(path=path, session_id="s")
    assert resp.content == "from disk"


async def test_resolve_with_none_falls_back_to_disk(tmp_path):
    """A path outside the server root resolves to None (handler short-circuit),
    which must drop through to disk rather than hang."""
    client = HarnessClient()
    path = str(tmp_path / "outside.txt")
    with open(path, "w") as fh:
        fh.write("disk content")
    client.set_fs_handler(lambda rid, payload: client.resolve_fs(rid, None))

    resp = await client.read_text_file(path=path, session_id="s")
    assert resp.content == "disk content"

    path2 = str(tmp_path / "w.txt")
    await client.write_text_file(content="written", path=path2, session_id="s")
    with open(path2) as fh:
        assert fh.read() == "written"
