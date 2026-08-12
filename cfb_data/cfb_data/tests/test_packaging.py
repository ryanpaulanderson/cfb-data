"""Tests for the installable package boundary."""

from importlib.metadata import version
from importlib.resources import files

import cfb_data


def test_distribution_and_package_are_importable() -> None:
    """Verify an editable install exposes the package and its metadata."""
    assert cfb_data.__doc__
    assert version("cfb-data") == "0.1.0"
    assert files(cfb_data).joinpath("py.typed").is_file()
