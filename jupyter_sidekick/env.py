"""Environment variable passthrough policy for harness subprocesses.

ACP's ``spawn_stdio_transport`` intentionally uses a minimal environment
(HOME, PATH, SHELL, TERM, USER, LOGNAME) following MCP best-practice
sandboxing for third-party tool servers.  Harnesses are first-party agent
CLIs running as the same user as the Jupyter server, so the minimal default
breaks legitimate workflows — tools like ``gh`` rely on XDG_CONFIG_HOME,
and JupyterHub admins deliberately construct the user environment via the
hub helm chart.

``compute_harness_env`` bridges the gap by merging ``os.environ`` into the
dict passed to the harness subprocess according to a user-configurable policy.
"""
from __future__ import annotations

import os
from typing import Dict, Mapping, Optional


def compute_harness_env(
    policy: str,
    spec_env: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    """Return the env dict to pass to a harness subprocess.

    Parameters
    ----------
    policy:
        ``"all"`` — inherit the full ``os.environ`` (default).
        ``"xdg"`` — ACP minimal defaults + every ``XDG_*`` variable.
        ``"minimal"`` — pass nothing; ACP supplies its own defaults.
        ``"VAR1,VAR2,..."`` — pass only the named variables (if present).
    spec_env:
        Per-harness env overrides from ``HarnessSpec.env``; merged last so
        they win over anything computed from the policy.
    """
    policy = policy.strip()
    if policy == "all":
        merged: Dict[str, str] = dict(os.environ)
    elif policy == "minimal":
        merged = {}
    elif policy == "xdg":
        merged = {k: v for k, v in os.environ.items() if k.startswith("XDG_")}
    else:
        keys = [k.strip() for k in policy.split(",") if k.strip()]
        merged = {k: os.environ[k] for k in keys if k in os.environ}
    if spec_env:
        merged.update(spec_env)
    return merged
