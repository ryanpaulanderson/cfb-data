"""Pydantic-validating games API client."""

from cfb_data.base.validation.validation_api import CFBDValidationAPI

from ..api.game_api import CFBDGamesAPI


class CFBDGamesValidationAPI(CFBDGamesAPI, CFBDValidationAPI):
    """Games API client that validates responses using Pydantic models."""

    pass
