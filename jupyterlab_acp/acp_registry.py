"""Integration with the shared ACP Agent Registry.

The registry (https://agentclientprotocol.com, jointly maintained by Zed and
JetBrains) is a public JSON index of ACP agents. Each entry has a `distribution`
describing how to launch it:

- `npx` / `uvx` — runnable on demand (no separate install step);
- `binary` — a per-platform archive we download + extract + cache on first use.

This is how we emulate Zed's "add more agents" marketplace using the community
asset rather than a hand-maintained list.
"""
from __future__ import annotations

import io
import json
import os
import platform
import shutil
import stat
import tarfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .registry import HarnessSpec

REGISTRY_URL = "https://cdn.agentclientprotocol.com/registry/v1/latest/registry.json"
_USER_AGENT = "jupyterlab-acp"
_SUPPORTED_ARCHIVES = (".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".tar", ".zip")

_SYSTEMS = {"Linux": "linux", "Darwin": "darwin", "Windows": "windows"}
_ARCHES = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}


def platform_key(system: str, machine: str) -> Optional[str]:
    """Map (platform.system(), platform.machine()) to a registry platform key."""
    sysname = _SYSTEMS.get(system)
    arch = _ARCHES.get(machine.lower())
    return f"{sysname}-{arch}" if sysname and arch else None


def current_platform_key() -> Optional[str]:
    return platform_key(platform.system(), platform.machine())


def _download_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as resp:
        return resp.read()


def _extract(data: bytes, url: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if url.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            zf.extractall(dest)
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
            tf.extractall(dest, filter="data")  # filter guards path traversal


def spec_from_distribution(agent: Dict[str, Any]) -> Optional[HarnessSpec]:
    """Derive a runnable HarnessSpec from an npx/uvx distribution, or None.
    Binary distributions are handled separately (they require a download)."""
    dist = agent.get("distribution", {})
    agent_id = agent["id"]
    name = agent.get("name", agent_id)
    if "npx" in dist:
        npx = dist["npx"]
        return HarnessSpec(
            id=agent_id, display_name=name, command="npx",
            args=("-y", npx["package"], *tuple(npx.get("args", []))),
        )
    if "uvx" in dist:
        uvx = dist["uvx"]
        return HarnessSpec(
            id=agent_id, display_name=name, command="uvx",
            args=(uvx["package"], *tuple(uvx.get("args", []))),
        )
    return None


def binary_spec(
    agent: Dict[str, Any],
    plat: str,
    cache_root,
    download: Callable[[str], bytes] = _download_bytes,
) -> Optional[HarnessSpec]:
    """Download + extract (cached) the platform binary and return a HarnessSpec,
    or None if there's no supported archive for this platform."""
    entry = agent.get("distribution", {}).get("binary", {}).get(plat)
    if not entry or not entry.get("archive", "").endswith(_SUPPORTED_ARCHIVES):
        return None
    agent_id = agent["id"]
    dest = Path(cache_root) / agent_id / str(agent.get("version", "")) / plat
    cmd = (dest / entry["cmd"]).resolve()
    if not cmd.exists():
        _extract(download(entry["archive"]), entry["archive"], dest)
    if not cmd.exists():
        return None
    mode = os.stat(cmd).st_mode
    os.chmod(cmd, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return HarnessSpec(
        id=agent_id,
        display_name=agent.get("name", agent_id),
        command=str(cmd),
        args=tuple(entry.get("args", ())),
        env=entry.get("env"),
    )


class AcpRegistry:
    """Lazily-fetched, cached view of the shared ACP Agent Registry."""

    def __init__(
        self,
        url: str = REGISTRY_URL,
        fetch: Optional[Callable[[], Dict[str, Any]]] = None,
        cache_root=None,
        which: Callable[[str], Optional[str]] = shutil.which,
    ) -> None:
        self._url = url
        self._fetch = fetch or self._default_fetch
        self._cache_root = Path(cache_root or Path.home() / ".cache" / "jupyterlab-acp" / "agents")
        self._platform = current_platform_key()
        self._which = which  # resolve a runtime (npx/uvx) on PATH; injectable for tests
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._loaded = False

    def _default_fetch(self) -> Dict[str, Any]:
        request = urllib.request.Request(self._url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(request, timeout=10) as resp:
            return json.loads(resp.read())

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        try:
            data = self._fetch()
            self._agents = {a["id"]: a for a in data.get("agents", [])}
        except Exception:
            self._agents = {}  # offline / fetch failure: degrade quietly
        self._loaded = True

    def _launchable(self, agent: Dict[str, Any]) -> bool:
        # npx/uvx agents are only launchable if that runtime is on PATH; binary
        # agents only if there's a supported archive for this platform.
        dist = agent.get("distribution", {})
        if "npx" in dist:
            return self._which("npx") is not None
        if "uvx" in dist:
            return self._which("uvx") is not None
        if self._platform:
            entry = dist.get("binary", {}).get(self._platform)
            return bool(entry and entry.get("archive", "").endswith(_SUPPORTED_ARCHIVES))
        return False

    def get(self, agent_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_loaded()
        return self._agents.get(agent_id)

    def spec_for(self, agent_id: str) -> Optional[HarnessSpec]:
        """Resolve a launch spec, downloading the binary if needed (blocking —
        callers run this off the event loop)."""
        agent = self.get(agent_id)
        if agent is None:
            return None
        spec = spec_from_distribution(agent)
        if spec is not None:
            return spec
        if self._platform:
            return binary_spec(agent, self._platform, self._cache_root)
        return None

    def listing(self) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        return [
            {
                "id": a["id"],
                "display_name": a.get("name", a["id"]),
                "description": a.get("description"),
                "icon": a.get("icon"),
                "launchable": self._launchable(a),
                "requires_download": "binary" in a.get("distribution", {}),
            }
            for a in self._agents.values()
        ]
