"""Drive endpoint handlers for the CFBD API."""

from __future__ import annotations

from typing import Any, Dict, List

from cfb_data.base.api.base_api import CFBDAPIBase, route
from cfb_data.drives.models.pandera.responses import DriveSchema
from cfb_data.drives.models.pydantic.responses import Drive


class CFBDDrivesAPI(CFBDAPIBase):
    """Drives endpoint for the College Football Data API."""

    @route("/drives", response_model=Drive, dataframe_schema=DriveSchema)
    async def _get_drives(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Retrieve historical drive data.

        :param params: Query parameters including year (required) and optional
            filters such as week, team, offense, defense, conference, and
            classification.
        :type params: Dict[str, Any]
        :return: List of drive dictionaries.
        :rtype: List[Dict[str, Any]]
        :raises ValueError: If the required ``year`` parameter is missing.
        """

        if "year" not in params:
            raise ValueError("year parameter is required for /drives endpoint")

        return await self._make_request("/drives", params)
