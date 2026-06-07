"""The shared ACP Agent Registry (Zed + JetBrains): parse the index and derive
on-demand launch specs from npx/uvx distributions."""
from __future__ import annotations

import io
import os
import tarfile

from jupyterlab_acp.acp_registry import (
    AcpRegistry,
    binary_spec,
    platform_key,
    spec_from_distribution,
)

SAMPLE = {
    "version": "1",
    "agents": [
        {
            "id": "cline",
            "name": "Cline",
            "description": "Autonomous coding agent",
            "icon": "https://x/cline.svg",
            "distribution": {"npx": {"package": "cline@3.0.17", "args": ["--acp"]}},
        },
        {
            "id": "fast-agent",
            "name": "fast-agent",
            "distribution": {"uvx": {"package": "fast-agent-acp", "args": ["acp"]}},
        },
        {
            "id": "somebin",
            "name": "SomeBin",
            "distribution": {"binary": {"linux-x86_64": {"archive": "u", "cmd": "bin/x"}}},
        },
    ],
}


def test_spec_from_npx_distribution():
    spec = spec_from_distribution(SAMPLE["agents"][0])
    assert spec.id == "cline"
    assert spec.command == "npx"
    assert spec.args == ("-y", "cline@3.0.17", "--acp")


def test_spec_from_uvx_distribution():
    spec = spec_from_distribution(SAMPLE["agents"][1])
    assert spec.command == "uvx"
    assert spec.args == ("fast-agent-acp", "acp")


def test_binary_distribution_not_launchable_yet():
    assert spec_from_distribution(SAMPLE["agents"][2]) is None


def test_registry_listing_and_spec_for():
    # `which` returns a path for every runtime → npx/uvx agents are launchable.
    registry = AcpRegistry(fetch=lambda: SAMPLE, which=lambda c: f"/usr/bin/{c}")
    listing = {a["id"]: a for a in registry.listing()}
    assert listing["cline"]["launchable"] is True
    assert listing["cline"]["display_name"] == "Cline"
    assert listing["somebin"]["launchable"] is False
    assert registry.spec_for("cline").command == "npx"
    assert registry.spec_for("missing") is None
    # npx/uvx run on demand; binary distributions download + extract on first use.
    assert listing["cline"]["requires_download"] is False
    assert listing["fast-agent"]["requires_download"] is False
    assert listing["somebin"]["requires_download"] is True


def test_not_launchable_when_runtime_missing():
    # npx not on PATH → the npx agent (cline) is not offered; uvx still is.
    registry = AcpRegistry(
        fetch=lambda: SAMPLE,
        which=lambda c: None if c == "npx" else f"/usr/bin/{c}",
    )
    listing = {a["id"]: a for a in registry.listing()}
    assert listing["cline"]["launchable"] is False
    assert listing["fast-agent"]["launchable"] is True


def test_offline_safe():
    def boom():
        raise OSError("no network")

    registry = AcpRegistry(fetch=boom)
    assert registry.listing() == []  # degrades quietly, never raises


def test_platform_key_mapping():
    assert platform_key("Linux", "x86_64") == "linux-x86_64"
    assert platform_key("Darwin", "arm64") == "darwin-aarch64"
    assert platform_key("Windows", "AMD64") == "windows-x86_64"
    assert platform_key("Plan9", "sparc") is None


def _targz(name: str, content: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name=name)
        info.size = len(content)
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def test_binary_spec_downloads_and_extracts(tmp_path):
    agent = {
        "id": "demo",
        "name": "Demo",
        "version": "1.0",
        "distribution": {
            "binary": {"linux-x86_64": {"archive": "https://x/demo.tar.gz", "cmd": "demo-acp"}}
        },
    }
    data = _targz("demo-acp", b"#!/bin/sh\necho hi\n")
    spec = binary_spec(agent, "linux-x86_64", tmp_path, download=lambda url: data)
    assert spec is not None
    assert spec.command.endswith("demo-acp")
    assert os.path.exists(spec.command)
    assert os.access(spec.command, os.X_OK)


def test_binary_unsupported_archive_not_launchable(tmp_path):
    agent = {
        "id": "x",
        "name": "X",
        "distribution": {"binary": {"linux-x86_64": {"archive": "https://x/x.rar", "cmd": "x"}}},
    }
    assert binary_spec(agent, "linux-x86_64", tmp_path, download=lambda url: b"") is None
