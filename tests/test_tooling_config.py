"""Tests for Task 2: Tooling configuration (pre-commit, mypy strict).

Asserts that the required config files exist and contain the correct settings.
"""

import subprocess
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).parent.parent


@pytest.mark.unit
def test_pre_commit_config_exists() -> None:
    """The .pre-commit-config.yaml file must exist at the repo root."""
    config = REPO_ROOT / ".pre-commit-config.yaml"
    assert config.exists(), f"Missing .pre-commit-config.yaml at {config}"


@pytest.mark.unit
def test_pre_commit_config_has_ruff_hook() -> None:
    """The pre-commit config must include the ruff hook."""
    config = REPO_ROOT / ".pre-commit-config.yaml"
    data = yaml.safe_load(config.read_text())
    repo_urls = [r["repo"] for r in data["repos"]]
    assert any("ruff" in url for url in repo_urls), (
        "Expected a ruff repo in .pre-commit-config.yaml"
    )
    # Verify both ruff and ruff-format hooks exist under the ruff repo
    ruff_repos = [r for r in data["repos"] if "ruff" in r["repo"]]
    assert len(ruff_repos) == 1
    hook_ids = [h["id"] for h in ruff_repos[0]["hooks"]]
    assert "ruff" in hook_ids, "ruff check hook missing"
    assert "ruff-format" in hook_ids, "ruff-format hook missing"


@pytest.mark.unit
def test_pre_commit_config_has_mypy_hook() -> None:
    """The pre-commit config must include the mypy hook with --strict arg."""
    config = REPO_ROOT / ".pre-commit-config.yaml"
    data = yaml.safe_load(config.read_text())
    mypy_repos = [r for r in data["repos"] if "mypy" in r["repo"]]
    assert len(mypy_repos) == 1, "Expected exactly one mypy repo in .pre-commit-config.yaml"
    mypy_hooks = [h for h in mypy_repos[0]["hooks"] if h["id"] == "mypy"]
    assert len(mypy_hooks) == 1, "Expected exactly one mypy hook"
    hook = mypy_hooks[0]
    assert "--strict" in hook.get("args", []), "mypy hook must include --strict in args"


@pytest.mark.unit
def test_mypy_ini_exists() -> None:
    """mypy.ini must exist at the repo root."""
    ini = REPO_ROOT / "mypy.ini"
    assert ini.exists(), f"Missing mypy.ini at {ini}"


@pytest.mark.unit
def test_mypy_ini_has_strict() -> None:
    """mypy.ini must enable strict mode."""
    import configparser

    ini = REPO_ROOT / "mypy.ini"
    cp = configparser.ConfigParser()
    cp.read(ini)
    assert "mypy" in cp, "mypy.ini must have a [mypy] section"
    strict_val = cp["mypy"].get("strict", "").strip().lower()
    assert strict_val in ("true", "1", "yes"), (
        f"mypy.ini [mypy] strict must be True, got {strict_val!r}"
    )


@pytest.mark.unit
def test_mypy_ini_python_version() -> None:
    """mypy.ini must target Python 3.12."""
    import configparser

    ini = REPO_ROOT / "mypy.ini"
    cp = configparser.ConfigParser()
    cp.read(ini)
    py_version = cp["mypy"].get("python_version", "").strip()
    assert py_version == "3.12", f"mypy.ini [mypy] python_version must be 3.12, got {py_version!r}"


@pytest.mark.unit
def test_mypy_passes_strict_on_src() -> None:
    """Running mypy --strict on src/ must succeed with zero issues."""
    result = subprocess.run(
        ["uv", "run", "--no-sync", "mypy", "src/", "--strict"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"mypy --strict on src/ failed:\n{result.stdout}\n{result.stderr}"
    )
