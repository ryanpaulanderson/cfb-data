"""Validation helpers for CFBD API responses."""

from typing import Any, Dict, List, Optional, Type, TypeVar, Union

from cfb_data.base.api.base_api import CFBDAPIBase
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class CFBDValidationAPI(CFBDAPIBase):
    """Base API client that validates responses using Pydantic models."""

    async def make_request_validated(
        self,
        path: str,
        model: Type[T],
        params: Optional[Dict[str, Any]] = None,
    ) -> Union[T, List[T]]:
        """Make a request and validate the JSON response.

        :param path: API endpoint path to request
        :type path: str
        :param model: Pydantic model class used for validation
        :type model: Type[T]
        :param params: Optional query parameters for the request
        :type params: Optional[Dict[str, Any]]
        :return: Validated model instance or list of instances
        :rtype: Union[T, List[T]]
        :raises TypeError: If the returned data is not a ``list`` or ``dict``
        """
        data: Union[List[Any], Dict[str, Any]] = await self.make_request(path, params)
        if isinstance(data, list):
            return [model.model_validate(item) for item in data]
        if isinstance(data, dict):
            return model.model_validate(data)
        raise TypeError("Response data must be list or dict")
