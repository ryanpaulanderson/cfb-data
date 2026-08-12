"""Tests for the installable package boundary."""

from importlib.metadata import version
from importlib.resources import files

import cfb_data.conferences
import cfb_data.drives
import cfb_data.games
import cfb_data.plays
import cfb_data.teams
import cfb_data.venues

import cfb_data


def test_distribution_and_package_are_importable() -> None:
    """Verify an editable install exposes the package and its metadata."""
    assert cfb_data.__doc__
    assert version("cfb-data") == "0.2.0"
    assert files(cfb_data).joinpath("py.typed").is_file()


def test_legacy_clients_and_generic_routing_are_not_exported() -> None:
    """Keep the 0.2.0 package surface free of compatibility wrappers."""
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
    assert not hasattr(cfb_data.CFBDClient("key"), "make_request")
