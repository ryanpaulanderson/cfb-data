"""Pandas-returning games API client."""

import pandas as pd
from cfb_data.base.pandas.pandas_api import CFBDPandasAPI

from ..validation.game_validation import CFBDGamesValidationAPI


class CFBDGamesPandasAPI(CFBDGamesValidationAPI, CFBDPandasAPI):
    """Games API client that converts responses to :class:`pandas.DataFrame`."""

    pass
