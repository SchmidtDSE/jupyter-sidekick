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
import socket
import subprocess
import sys
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
