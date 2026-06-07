"""REST handler integration tests against a real Jupyter Server subprocess.

A synchronous HTTP client against an out-of-process server — avoids the
event-loop conflict between pytest-asyncio and in-process server fixtures, and
exercises the real routes, token auth, and XSRF behaviour. Bind-success (which
launches a harness) is covered by test_manager.py; here we cover the HTTP
contract: listing, unbound state, error mapping, and auth enforcement.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

import pytest


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _request(base, token, path, method="GET", body=None, auth=True):
    url = f"{base}/jupyterlab_acp/{path}"
    headers = {}
    if auth:
        headers["Authorization"] = f"token {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, None


@pytest.fixture(scope="module")
def server():
    port = _free_port()
    token = "test-token"
    base = f"http://127.0.0.1:{port}"
    # Run jupyter_server as a module in *this* interpreter (the venv), so our
    # editable-installed extension is loaded. `-m jupyter server` would instead
    # dispatch to whatever `jupyter-server` is first on PATH.
    # Isolate JUPYTER_DATA_DIR so the chat index starts empty and doesn't touch
    # the developer's real history file.
    data_dir = tempfile.mkdtemp(prefix="jacp-test-data-")
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "jupyter_server",
            f"--ServerApp.port={port}",
            f"--ServerApp.token={token}",
            "--ServerApp.open_browser=False",
            "--ServerApp.root_dir=/tmp",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "JUPYTER_DATA_DIR": data_dir},
    )
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                code, _ = _request(base, token, "harnesses")
                if code == 200:
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            pytest.fail("jupyter server did not come up")
        yield base, token
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        shutil.rmtree(data_dir, ignore_errors=True)


def test_lists_default_harnesses(server):
    base, token = server
    code, body = _request(base, token, "harnesses")
    assert code == 200
    assert "claude-code" in [h["id"] for h in body["harnesses"]]


def test_unbound_state_returns_null(server):
    base, token = server
    code, body = _request(base, token, "chats/absent/state")
    assert code == 200
    assert body == {"harness_id": None}


def test_bind_unknown_harness_404(server):
    base, token = server
    code, _ = _request(base, token, "chats/c1/bind", method="POST", body={"harness_id": "nope"})
    assert code == 404


def test_bind_missing_harness_id_400(server):
    base, token = server
    code, _ = _request(base, token, "chats/c1/bind", method="POST", body={})
    assert code == 400


def test_requires_auth(server):
    base, token = server
    code, _ = _request(base, token, "harnesses", auth=False)
    assert code in (401, 403)


def test_close_unbound_chat_is_idempotent(server):
    # Closing a chat that was never bound (or already closed) is a no-op success,
    # so the client can fire it on reset/dispose without tracking bind state.
    base, token = server
    code, body = _request(base, token, "chats/never-bound/close", method="POST", body={})
    assert code == 200
    assert body == {"ok": True}


def test_chats_list_starts_empty(server):
    # With an isolated data dir and no binds, the resume list is empty.
    base, token = server
    code, body = _request(base, token, "chats")
    assert code == 200
    assert body == {"chats": []}


def test_resume_unknown_chat_404(server):
    base, token = server
    code, _ = _request(base, token, "chats/never-recorded/resume", method="POST", body={})
    assert code == 404


async def test_stream_websocket_rejects_unauthenticated(server):
    # The streaming websocket must authenticate the upgrade like jupyter_server's
    # own websockets — an unauthenticated connect is refused, not opened.
    import tornado.websocket
    from tornado.httpclient import HTTPClientError

    base, _token = server
    ws_url = base.replace("http://", "ws://") + "/jupyterlab_acp/chats/x/stream"
    with pytest.raises(HTTPClientError) as exc:
        await tornado.websocket.websocket_connect(ws_url)
    assert exc.value.code in (401, 403)


# --- resolve_cwd (pure; no server needed) -------------------------------------
# Regression coverage for the 502 where an unexpanded/missing working directory
# was reported as a "command not installed on PATH" launch failure.
from jupyterlab_acp.handlers import resolve_cwd  # noqa: E402

_HOME_PROJ = os.path.expanduser("~/proj")


@pytest.mark.parametrize(
    "requested, server_root, env, existing, expected",
    [
        # requested exists -> returned as-is
        ("/exists", "/root", {}, {"/exists"}, "/exists"),
        # a literal "~" is expanded before the existence check
        ("~/proj", None, {}, {_HOME_PROJ}, _HOME_PROJ),
        # "$VARS" are expanded
        ("$WORK/x", None, {"WORK": "/work"}, {"/work/x"}, "/work/x"),
        # requested missing -> fall back to the server root
        ("/gone", "/root", {}, {"/root"}, "/root"),
        # nothing exists -> None, so the subprocess inherits the server's cwd
        ("/gone", "/also-gone", {}, set(), None),
        # empty requested is skipped, not treated as a path
        ("", "/root", {}, {"/root"}, "/root"),
    ],
)
def test_resolve_cwd(requested, server_root, env, existing, expected, monkeypatch):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(os.path, "isdir", lambda p: p in existing)
    assert resolve_cwd(requested, server_root) == expected
