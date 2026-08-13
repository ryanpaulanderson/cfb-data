"""Tests for the installable package boundary."""

from importlib.metadata import metadata, version
from importlib.resources import files as resource_files
from pathlib import Path

import cfb_data.adjusted_metrics
import cfb_data.conferences
import cfb_data.draft
import cfb_data.drives
import cfb_data.games
import cfb_data.info
import cfb_data.playoffs
import cfb_data.plays
import cfb_data.teams
import cfb_data.venues

import cfb_data


def test_distribution_and_package_are_importable() -> None:
    """Verify an editable install exposes the package and its metadata."""
    assert cfb_data.__doc__
    assert version("cfb-data") == "0.4.1"
    assert resource_files(cfb_data).joinpath("py.typed").is_file()


def test_distribution_requires_supported_python_versions() -> None:
    """Verify package metadata advertises the supported Python versions."""
    distribution_metadata = metadata("cfb-data")
    classifiers = distribution_metadata.get_all("Classifier")

    assert distribution_metadata["Requires-Python"] == ">=3.12"
    assert classifiers is not None
    assert "Programming Language :: Python :: 3.11" not in classifiers
    assert "Programming Language :: Python :: 3.12" in classifiers
    assert "Programming Language :: Python :: 3.13" in classifiers


def test_project_license_matches_distribution_metadata() -> None:
    """Verify package metadata and the project license agree on MIT."""
    distribution_metadata = metadata("cfb-data")
    project_license = Path(__file__).resolve().parents[3] / "LICENSE"

    assert distribution_metadata["License-Expression"] == "MIT"
    assert distribution_metadata.get_all("License-File") == ["LICENSE"]
    assert project_license.read_text(encoding="utf-8").startswith(
        "MIT License\n\nCopyright (c) 2025-2026 Ryan Anderson\n"
    )


def test_release_workflow_uses_trusted_main_push() -> None:
    """Keep release execution on the trusted main push revision."""
    repository_root = Path(__file__).resolve().parents[3]
    workflow = (repository_root / ".github/workflows/release.yml").read_text(
        encoding="utf-8"
    )

    assert "\n  pull_request_target:" not in workflow
    assert "\n  push:\n    branches: [main]\n" in workflow
    assert "\n  workflow_dispatch:" not in workflow
    assert "needs.release.outputs.release_sha" not in workflow
    assert "ref: ${{ github.sha }}" in workflow
    assert workflow.count("id-token: write") == 1


def test_legacy_clients_and_generic_routing_are_not_exported() -> None:
    """Keep the 0.4.1 package surface free of compatibility wrappers."""
    legacy_names = {
        "CFBDAPIBase",
        "CFBDValidationAPI",
        "CFBDPandasAPI",
        "CFBDGamesAPI",
        "CFBDGamesValidationAPI",
        "CFBDGamesPandasAPI",
        "CFBDDrivesAPI",
        "CFBDDrivesValidationAPI",
        "CFBDDrivesPandasAPI",
        "CFBDPlaysAPI",
        "CFBDPlaysValidationAPI",
        "CFBDPlaysPandasAPI",
        "route",
    }

    assert legacy_names.isdisjoint(vars(cfb_data))
    assert legacy_names.isdisjoint(vars(cfb_data.games))
    assert legacy_names.isdisjoint(vars(cfb_data.drives))
    assert legacy_names.isdisjoint(vars(cfb_data.plays))
    assert legacy_names.isdisjoint(vars(cfb_data.venues))
    assert legacy_names.isdisjoint(vars(cfb_data.conferences))
    assert legacy_names.isdisjoint(vars(cfb_data.teams))
    assert legacy_names.isdisjoint(vars(cfb_data.draft))
    assert legacy_names.isdisjoint(vars(cfb_data.playoffs))
    assert legacy_names.isdisjoint(vars(cfb_data.adjusted_metrics))
    assert legacy_names.isdisjoint(vars(cfb_data.info))
    assert not hasattr(cfb_data.CFBDClient("key"), "make_request")
