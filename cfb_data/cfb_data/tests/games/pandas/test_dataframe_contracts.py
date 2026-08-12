"""Check that DataFrame columns track the validated API response contract."""

import pytest
from cfb_data.games.models.pandera.responses import (
    CalendarWeekSchema,
    GameMediaSchema,
    GameSchema,
    GameWeatherSchema,
    PlayerGameStatsSchema,
    ScoreboardSchema,
    TeamGameStatsSchema,
    TeamRecordsSchema,
)
from cfb_data.games.models.pydantic.responses import (
    CalendarWeek,
    Game,
    GameMedia,
    GameWeather,
    PlayerGameStats,
    ScoreboardGame,
    TeamGameStats,
    TeamRecords,
)
from pandera.pandas import DataFrameModel
from pydantic import BaseModel


@pytest.mark.parametrize(
    ("response_model", "dataframe_schema"),
    [
        (Game, GameSchema),
        (CalendarWeek, CalendarWeekSchema),
        (GameMedia, GameMediaSchema),
        (GameWeather, GameWeatherSchema),
        (TeamRecords, TeamRecordsSchema),
        (ScoreboardGame, ScoreboardSchema),
        (PlayerGameStats, PlayerGameStatsSchema),
        (TeamGameStats, TeamGameStatsSchema),
    ],
)
def test_dataframe_columns_match_response_model(
    response_model: type[BaseModel], dataframe_schema: type[DataFrameModel]
) -> None:
    """Expose every validated field once in the corresponding DataFrame."""
    assert set(dataframe_schema.to_schema().columns) == set(response_model.model_fields)
