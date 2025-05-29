"""Pandas wrapper for validated CFBD API responses."""

from typing import Any, Dict, List, Optional, Type, TypeVar, Union

import pandas as pd
from cfb_data.base.validation.validation_api import CFBDValidationAPI
from pandera import DataFrameModel
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class CFBDPanderaAPI(CFBDValidationAPI):
    """Base API client that returns Pandas DataFrames validated with pandera."""

    async def make_request_pandas(
        self,
        path: str,
        model: Type[T],
        schema: Type[DataFrameModel],
        params: Optional[Dict[str, Any]] = None,
    ) -> pd.DataFrame:
        """Make a request and return a validated :class:`pandas.DataFrame`.

        The JSON response is first parsed into ``model`` using ``pydantic`` and
        then coerced into a DataFrame validated against ``schema``.

        :param path: API endpoint path to request
        :type path: str
        :param model: Pydantic model class used for validation
        :type model: Type[T]
        :param schema: Pandera schema model for DataFrame validation
        :type schema: Type[DataFrameModel]
        :param params: Optional query parameters for the request
        :type params: Optional[Dict[str, Any]]
        :return: Validated DataFrame containing the response data
        :rtype: pandas.DataFrame
        """
        data: Union[List[T], T] = await self.make_request_validated(path, model, params)

        records: List[Dict[str, Any]]
        if isinstance(data, list):
            records = [d.model_dump() for d in data]
        else:
            records = [data.model_dump()]

        df: pd.DataFrame = pd.DataFrame(records)
        validated_df: pd.DataFrame = schema.validate(df)
        return validated_df
