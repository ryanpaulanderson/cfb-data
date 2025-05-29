"""Pydantic-validating drives API client."""

from cfb_data.base.validation.validation_api import CFBDValidationAPI

from ..api.drives_api import CFBDDrivesAPI


class CFBDDrivesValidationAPI(CFBDDrivesAPI, CFBDValidationAPI):
    """Drives API client that validates responses using Pydantic models."""

    pass
