"""Tests for the installable package boundary."""

from importlib.metadata import version

import cfb_data


def test_distribution_and_package_are_importable() -> None:
    """Verify an editable install exposes the package and its metadata."""

    assert cfb_data.__doc__
    assert version("cfb-data") == "0.1.0"
