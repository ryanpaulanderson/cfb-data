"""Drive endpoint handlers for the CFBD API."""

from __future__ import annotations

from cfb_data.base.api.base_api import CFBDAPIBase, route
from cfb_data.base.types import (
    JSONObject,
    QueryParameters,
    json_object_list,
    query_parameters,
)
from cfb_data.drives.models.pandera.responses import DriveSchema
from cfb_data.drives.models.pydantic.requests import DrivesRequest
from cfb_data.drives.models.pydantic.responses import Drive


class CFBDDrivesAPI(CFBDAPIBase):
    """Drives endpoint for the College Football Data API."""

    @route("/drives", response_model=Drive, dataframe_schema=DriveSchema)
    async def _get_drives(self, params: QueryParameters) -> list[JSONObject]:
        """Retrieve historical drive data.

        :param params: Query parameters including year (required) and optional
            filters such as week, team, offense, defense, conference, and
            classification.
        :type params: Dict[str, Any]
        :return: List of drive dictionaries.
        :rtype: List[Dict[str, Any]]
        :raises ValidationError: If required parameters are missing or invalid.
        """
        # Validate using request model instead of hard-coded check
        request: DrivesRequest = DrivesRequest.model_validate(params)
        validated_params = query_parameters(
            request.model_dump(exclude_none=True, by_alias=True)
        )
        return json_object_list(await self._make_request("/drives", validated_params))
