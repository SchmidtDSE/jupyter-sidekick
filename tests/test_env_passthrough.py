"""compute_harness_env: policy-driven env var passthrough for harness subprocesses."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from jupyter_sidekick.env import compute_harness_env


FAKE_ENV = {
    "HOME": "/home/user",
    "PATH": "/usr/bin:/bin",
    "XDG_CONFIG_HOME": "/opt/share/xdg-config",
    "XDG_DATA_HOME": "/opt/share/xdg-data",
    "GH_TOKEN": "ghp_secret",
    "ANTHROPIC_API_KEY": "sk-secret",
    "UNRELATED": "value",
}


@pytest.fixture(autouse=True)
def patched_env():
    with patch.dict(os.environ, FAKE_ENV, clear=True):
        yield


class TestAllPolicy:
    def test_inherits_full_env(self):
        result = compute_harness_env("all")
        assert result["GH_TOKEN"] == "ghp_secret"
        assert result["XDG_CONFIG_HOME"] == "/opt/share/xdg-config"
        assert result["UNRELATED"] == "value"

    def test_spec_env_overrides_inherited(self):
        result = compute_harness_env("all", {"GH_TOKEN": "override"})
        assert result["GH_TOKEN"] == "override"
        assert result["XDG_CONFIG_HOME"] == "/opt/share/xdg-config"


class TestXdgPolicy:
    def test_includes_xdg_vars(self):
        result = compute_harness_env("xdg")
        assert result["XDG_CONFIG_HOME"] == "/opt/share/xdg-config"
        assert result["XDG_DATA_HOME"] == "/opt/share/xdg-data"

    def test_excludes_non_xdg_secrets(self):
        result = compute_harness_env("xdg")
        assert "GH_TOKEN" not in result
        assert "ANTHROPIC_API_KEY" not in result
        assert "UNRELATED" not in result

    def test_spec_env_overrides(self):
        result = compute_harness_env("xdg", {"EXTRA": "yes"})
        assert result["EXTRA"] == "yes"
        assert result["XDG_CONFIG_HOME"] == "/opt/share/xdg-config"


class TestMinimalPolicy:
    def test_returns_empty_dict(self):
        result = compute_harness_env("minimal")
        assert result == {}

    def test_spec_env_still_applied(self):
        result = compute_harness_env("minimal", {"FOO": "bar"})
        assert result == {"FOO": "bar"}


class TestListPolicy:
    def test_passes_named_vars(self):
        result = compute_harness_env("GH_TOKEN,ANTHROPIC_API_KEY")
        assert result["GH_TOKEN"] == "ghp_secret"
        assert result["ANTHROPIC_API_KEY"] == "sk-secret"
        assert "UNRELATED" not in result

    def test_skips_missing_vars(self):
        result = compute_harness_env("GH_TOKEN,DOES_NOT_EXIST")
        assert result["GH_TOKEN"] == "ghp_secret"
        assert "DOES_NOT_EXIST" not in result

    def test_spec_env_overrides(self):
        result = compute_harness_env("GH_TOKEN", {"GH_TOKEN": "override"})
        assert result["GH_TOKEN"] == "override"

    def test_whitespace_in_list_is_stripped(self):
        result = compute_harness_env("GH_TOKEN , ANTHROPIC_API_KEY")
        assert "GH_TOKEN" in result
        assert "ANTHROPIC_API_KEY" in result


class TestResolveEnvPassthrough:
    """resolve_env_passthrough: traitlet value > env var > 'all'."""

    def test_reads_sidekick_env_passthrough_env_var(self):
        from jupyter_sidekick.extension import resolve_env_passthrough

        with patch.dict(os.environ, {"SIDEKICK_ENV_PASSTHROUGH": "minimal"}, clear=False):
            assert resolve_env_passthrough() == "minimal"

    def test_defaults_to_all_when_env_var_absent(self):
        from jupyter_sidekick.extension import resolve_env_passthrough

        env_without = {k: v for k, v in os.environ.items() if k != "SIDEKICK_ENV_PASSTHROUGH"}
        with patch.dict(os.environ, env_without, clear=True):
            assert resolve_env_passthrough() == "all"

    def test_explicit_value_overrides_env_var(self):
        from jupyter_sidekick.extension import resolve_env_passthrough

        with patch.dict(os.environ, {"SIDEKICK_ENV_PASSTHROUGH": "minimal"}, clear=False):
            assert resolve_env_passthrough("xdg") == "xdg"
