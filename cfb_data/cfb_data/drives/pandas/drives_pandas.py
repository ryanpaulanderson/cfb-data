"""Pandas-returning drives API client."""

import pandas as pd
from cfb_data.base.pandas.pandas_api import CFBDPandasAPI

from ..validation.drives_validation import CFBDDrivesValidationAPI


class CFBDDrivesPandasAPI(CFBDDrivesValidationAPI, CFBDPandasAPI):
    """Drives API client that converts responses to :class:`pandas.DataFrame`."""

    pass
