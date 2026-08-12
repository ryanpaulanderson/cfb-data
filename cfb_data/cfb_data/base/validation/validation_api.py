"""Validation layer for CFBD API clients using Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel

from cfb_data.base.api.base_api import CFBDAPIBase
from cfb_data.base.types import JSONResponse, QueryParameters, json_response

ValidatedResponse = list[BaseModel] | BaseModel | JSONResponse


class CFBDValidationAPI(CFBDAPIBase):
    """API client that automatically validates responses with Pydantic."""

    async def make_request(
        self, path: str, params: QueryParameters | None = None
    ) -> ValidatedResponse:
        """Return validated data for ``path``.

        The response model is obtained from the route decorator attached to the
        handler for ``path``. If no model is defined, the raw JSON is returned.

        :param path: API path to request.
        :type path: str
        :param params: Optional query parameters.
        :type params: Optional[Dict[str, Any]]
        :return: Validated models or raw JSON.
        :rtype: Union[List[BaseModel], BaseModel, Dict[str, Any], List[Dict[str, Any]]]
        :raises TypeError: If the response type is not list or dict when a model is provided.
        """
        data = json_response(await super().make_request(path, params))
        handler = self._route_map.get(path)
        model = getattr(handler, "response_model", None) if handler else None
        if model is None:
            return data
        if not isinstance(model, type) or not issubclass(model, BaseModel):
            raise TypeError("Route response model must be a Pydantic model class")

        if isinstance(data, list):
            return [model.model_validate(item) for item in data]
        if isinstance(data, dict):
            return model.model_validate(data)
        raise TypeError("Response data must be list or dict")
