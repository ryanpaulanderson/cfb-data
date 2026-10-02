"""Installed-distribution tests for user and official recipe-provider parity."""

from __future__ import annotations

import errno
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path


def test_installed_external_provider_uses_the_public_discovery_path(
    tmp_path: Path,
) -> None:
    """Build and install a separate provider without path injection or mocks."""
    fixture = Path(__file__).parent / "fixtures" / "external_recipe_provider"
    wheels = tmp_path / "wheels"
    wheels.mkdir()

    _run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(wheels),
            str(fixture),
        ]
    )
    built_wheels = tuple(wheels.glob("*.whl"))
    assert len(built_wheels) == 1
    environment = tmp_path / "environment"
    _run(
        [
            sys.executable,
            "-m",
            "venv",
            "--without-pip",
            str(environment),
        ]
    )
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    child_site = subprocess.run(
        [str(python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    # Clone installed dependencies without network access or shared installation writes.
    shutil.copytree(
        sysconfig.get_path("purelib"),
        child_site,
        copy_function=_link_or_copy,
        dirs_exist_ok=True,
    )
    _run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-deps",
            "--force-reinstall",
            str(built_wheels[0]),
        ]
    )
    script = """
import sys
from cfb_data.analytics import AnalyticsConfig, RecipeProviderTrust, discover_recipes

assert 'external_cfb_recipes' not in sys.modules
snapshot = discover_recipes(AnalyticsConfig(trusted_providers=(
    RecipeProviderTrust(
        distribution='cfb-data-test-recipes',
        entry_point='external',
        target='external_cfb_recipes',
        version='1.0.0',
    ),
)))
assert snapshot.count >= 3
assert 'external_cfb_recipes.example' in sys.modules
assert len(snapshot.fingerprint) == 64
"""
    try:
        _run([str(python), "-c", script])
    finally:
        _run(
            [
                str(python),
                "-m",
                "pip",
                "uninstall",
                "--yes",
                "cfb-data-test-recipes",
            ]
        )


def _run(command: list[str]) -> None:
    """Run one isolated packaging command with actionable captured output."""
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def _link_or_copy(source: str, destination: str) -> str:
    """Clone immutable installed files across an isolated environment boundary."""
    try:
        os.link(source, destination)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        return shutil.copy2(source, destination)
    return destination
