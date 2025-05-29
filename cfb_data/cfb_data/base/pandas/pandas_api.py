"""Pandas wrapper for validated CFBD API responses."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
from cfb_data.base.validation.validation_api import CFBDValidationAPI
from pydantic import BaseModel


class CFBDPandasAPI(CFBDValidationAPI):
    """API client that converts responses into ``pandas.DataFrame`` objects."""

    async def make_request(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> pd.DataFrame:
        """Return a DataFrame for ``path`` validated with Pandera if available.

        :param path: API path to request.
        :type path: str
        :param params: Optional query parameters.
        :type params: Optional[Dict[str, Any]]
        :return: Validated DataFrame of the response.
        :rtype: pandas.DataFrame
        """

        data = await super().make_request(path, params)
        handler = self._route_map.get(path)
        schema = getattr(handler, "dataframe_schema", None) if handler else None

        records: List[Dict[str, Any]]
        if isinstance(data, list):
            if data and isinstance(data[0], BaseModel):
                records = [d.model_dump() for d in data]
            else:
                records = [dict(item) for item in data]
        elif isinstance(data, BaseModel):
            records = [data.model_dump()]
        else:
            records = [dict(data)] if isinstance(data, dict) else []

        df = pd.DataFrame(records)
        if schema is not None:
            df = schema.validate(df)
        return df
