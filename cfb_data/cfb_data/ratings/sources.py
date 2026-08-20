"""Expose public validated Ratings sources for modular recipes."""

from __future__ import annotations

from typing import Literal

from cfb_data.analytics import SourceContext, source
from cfb_data.enums import Classification, SeasonType
from cfb_data.ratings._operations import (
    CONFERENCE_SP_RATINGS,
    CORE_RATINGS,
    ELO_RATINGS,
    EXPANDED_SRS_RATINGS,
    FPI_RATINGS,
    SP_RATINGS,
    SRS_RATINGS,
)
from cfb_data.ratings.models.pydantic.responses import (
    ConferenceSP,
    ExpandedTeamSRS,
    TeamCoreRating,
    TeamElo,
    TeamFPI,
    TeamSP,
    TeamSRS,
)

type _ClassificationArgument = Classification | Literal["fbs", "fcs", "ii", "iii"]
type _SeasonTypeArgument = (
    SeasonType
    | Literal[
        "regular",
        "postseason",
        "both",
        "allstar",
        "spring_regular",
        "spring_postseason",
    ]
)


@source(operation=CORE_RATINGS)
async def core_ratings(
    context: SourceContext[TeamCoreRating],
    *,
    year: int | None = None,
    team: str | None = None,
    conference: str | None = None,
) -> list[TeamCoreRating]:
    """Return validated CORE ratings in source order.

    :param context: Engine-owned source execution context.
    :param year: Optional rating season.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    :return: Source-faithful CORE rows.
    """
    return await context.retrieve(year=year, team=team, conference=conference)


@source(operation=SP_RATINGS)
async def sp_ratings(
    context: SourceContext[TeamSP],
    *,
    year: int | None = None,
    team: str | None = None,
) -> list[TeamSP]:
    """Return validated team SP+ ratings in source order.

    :param context: Engine-owned source execution context.
    :param year: Optional rating season.
    :param team: Optional team selector.
    :return: Source-faithful team SP+ rows.
    """
    return await context.retrieve(year=year, team=team)


@source(operation=CONFERENCE_SP_RATINGS)
async def conference_sp_ratings(
    context: SourceContext[ConferenceSP],
    *,
    year: int | None = None,
    conference: str | None = None,
    classification: _ClassificationArgument | None = None,
) -> list[ConferenceSP]:
    """Return validated conference SP+ ratings in source order.

    :param context: Engine-owned source execution context.
    :param year: Optional rating season.
    :param conference: Optional conference selector.
    :param classification: Optional classification selector.
    :return: Source-faithful conference SP+ rows.
    """
    return await context.retrieve(
        year=year,
        conference=conference,
        classification=classification,
    )


@source(operation=SRS_RATINGS)
async def srs_ratings(
    context: SourceContext[TeamSRS],
    *,
    year: int | None = None,
    team: str | None = None,
    conference: str | None = None,
) -> list[TeamSRS]:
    """Return validated SRS ratings in source order.

    :param context: Engine-owned source execution context.
    :param year: Optional rating season.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    :return: Source-faithful SRS rows.
    """
    return await context.retrieve(year=year, team=team, conference=conference)


@source(operation=EXPANDED_SRS_RATINGS)
async def expanded_srs_ratings(
    context: SourceContext[ExpandedTeamSRS],
    *,
    year: int | None = None,
    team: str | None = None,
    conference: str | None = None,
    classification: _ClassificationArgument | None = None,
) -> list[ExpandedTeamSRS]:
    """Return validated expanded SRS ratings in source order.

    :param context: Engine-owned source execution context.
    :param year: Optional rating season.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    :param classification: Optional classification selector.
    :return: Source-faithful expanded SRS rows.
    """
    return await context.retrieve(
        year=year,
        team=team,
        conference=conference,
        classification=classification,
    )


@source(operation=ELO_RATINGS)
async def elo_ratings(
    context: SourceContext[TeamElo],
    *,
    year: int | None = None,
    week: int | None = None,
    season_type: _SeasonTypeArgument | None = None,
    team: str | None = None,
    conference: str | None = None,
) -> list[TeamElo]:
    """Return validated Elo ratings in source order.

    :param context: Engine-owned source execution context.
    :param year: Optional rating season.
    :param week: Optional rating week.
    :param season_type: Optional season phase.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    :return: Source-faithful Elo rows.
    """
    return await context.retrieve(
        year=year,
        week=week,
        season_type=season_type,
        team=team,
        conference=conference,
    )


@source(operation=FPI_RATINGS)
async def fpi_ratings(
    context: SourceContext[TeamFPI],
    *,
    year: int | None = None,
    team: str | None = None,
    conference: str | None = None,
) -> list[TeamFPI]:
    """Return validated FPI ratings in source order.

    :param context: Engine-owned source execution context.
    :param year: Optional rating season.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    :return: Source-faithful FPI rows.
    """
    return await context.retrieve(year=year, team=team, conference=conference)


__all__ = [
    "conference_sp_ratings",
    "core_ratings",
    "elo_ratings",
    "expanded_srs_ratings",
    "fpi_ratings",
    "sp_ratings",
    "srs_ratings",
]
