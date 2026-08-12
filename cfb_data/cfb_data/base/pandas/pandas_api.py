"""Pandas wrapper for validated CFBD API responses."""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel

from cfb_data.base.types import JSONObject, QueryParameters, json_object
from cfb_data.base.validation.validation_api import CFBDValidationAPI


class CFBDPandasAPI(CFBDValidationAPI):
    """API client that converts responses into ``pandas.DataFrame`` objects."""

    async def make_request(
        self, path: str, params: QueryParameters | None = None
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

        records: list[JSONObject]
        if isinstance(data, list):
            if data and isinstance(data[0], BaseModel):
                records = [json_object(item.model_dump(mode="json")) for item in data]
            else:
                records = [json_object(item) for item in data]
        elif isinstance(data, BaseModel):
            records = [json_object(data.model_dump(mode="json"))]
        else:
            records = [data]

        df = pd.DataFrame(records)
        if schema is not None:
            df = schema.validate(df)
        return df
