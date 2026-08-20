"""Provide the independently authored long-form player-game-stat dataset.

``player_game_stats`` composes ``game_summaries`` with the public nested
``/games/players`` source. The source has no team ID, so each team is resolved
only within its validated game context through the explicit home/away side.
Every athlete statistic remains a display string, including compound values
such as ``7/9``; the recipe never guesses a numeric interpretation.
"""

from __future__ import annotations

from datetime import datetime

from cfb_data.analytics import RecipeRef, dataset, step
from cfb_data.enums import Classification, SeasonType
from cfb_data.games.models.pydantic.responses import PlayerGameStats
from cfb_data.games.sources import player_game_stats as player_game_stats_source
from pydantic import BaseModel, ConfigDict, Field

from cfb_data_recipes.game_summaries import GameSummary, game_summaries


class PlayerGameStat(BaseModel):
    """Represent one athlete statistic observation in one team/game context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    game_id: int = Field(ge=0, json_schema_extra={"semantic_type": "identifier"})
    season: int = Field(ge=0, json_schema_extra={"semantic_type": "dimension"})
    week: int = Field(ge=0, json_schema_extra={"semantic_type": "dimension"})
    season_type: SeasonType = Field(json_schema_extra={"semantic_type": "dimension"})
    start_date: datetime = Field(json_schema_extra={"semantic_type": "time"})
    team_id: int = Field(
        ge=0,
        description="Stable team ID resolved from the validated game side.",
        json_schema_extra={"semantic_type": "identifier"},
    )
    team: str = Field(
        description="Source team name retained from the player-stat response.",
        json_schema_extra={"semantic_type": "dimension"},
    )
    conference: str | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    classification: Classification | None = Field(
        default=None,
        description="Classification carried by the matching game side.",
        json_schema_extra={"semantic_type": "dimension"},
    )
    home_away: str = Field(pattern="^(home|away)$")
    team_ordinal: int = Field(
        ge=0,
        le=1,
        description="Zero for the home side and one for the away side.",
    )
    team_points: int | None = Field(
        default=None,
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    athlete_id: str = Field(json_schema_extra={"semantic_type": "identifier"})
    athlete_name: str = Field(json_schema_extra={"semantic_type": "dimension"})
    category: str = Field(json_schema_extra={"semantic_type": "dimension"})
    stat_type: str = Field(json_schema_extra={"semantic_type": "dimension"})
    stat: str = Field(
        description="Source display statistic preserved without numeric coercion.",
        json_schema_extra={"semantic_type": "text"},
    )
    category_ordinal: int = Field(ge=0)
    stat_type_ordinal: int = Field(ge=0)
    athlete_ordinal: int = Field(ge=0)


@step(
    id="cfbd.player_game_stats.flatten",
    revision=1,
    output=PlayerGameStat,
    deterministic=True,
)
def flatten_player_game_stats(
    summaries: list[GameSummary],
    nested: list[PlayerGameStats],
) -> list[PlayerGameStat]:
    """Flatten validated nesting using game-scoped side identity.

    :param summaries: Validated game contexts carrying stable team IDs.
    :param nested: Validated game/team/category/type/athlete source nesting.
    :return: Long-form statistic observations in deterministic source order.
    :raises ValueError: If a source game has no unique validated game context.
    """
    contexts: dict[int, GameSummary] = {}
    for summary in summaries:
        if summary.game_id in contexts:
            raise ValueError("Game summaries contain a duplicate game ID")
        contexts[summary.game_id] = summary

    rows: list[PlayerGameStat] = []
    for game in nested:
        context = contexts.get(game.id)
        if context is None:
            raise ValueError("Player statistics have no matching game context")
        for team in game.teams:
            home = team.home_away == "home"
            for category_ordinal, category in enumerate(team.categories):
                for stat_type_ordinal, stat_type in enumerate(category.types):
                    for athlete_ordinal, athlete in enumerate(stat_type.athletes):
                        rows.append(
                            PlayerGameStat(
                                game_id=game.id,
                                season=context.season,
                                week=context.week,
                                season_type=context.season_type,
                                start_date=context.start_date,
                                team_id=context.home_id if home else context.away_id,
                                team=team.team,
                                conference=team.conference,
                                classification=(
                                    context.home_classification
                                    if home
                                    else context.away_classification
                                ),
                                home_away=team.home_away,
                                team_ordinal=0 if home else 1,
                                team_points=team.points,
                                athlete_id=athlete.id,
                                athlete_name=athlete.name,
                                category=category.name,
                                stat_type=stat_type.name,
                                stat=athlete.stat,
                                category_ordinal=category_ordinal,
                                stat_type_ordinal=stat_type_ordinal,
                                athlete_ordinal=athlete_ordinal,
                            )
                        )
    return sorted(
        rows,
        key=lambda row: (
            row.season,
            row.week,
            row.game_id,
            row.team_ordinal,
            row.category_ordinal,
            row.stat_type_ordinal,
            row.athlete_ordinal,
        ),
    )


@dataset(
    id="cfbd.player_game_stats",
    revision=1,
    row=PlayerGameStat,
    grain="one athlete statistic observation in one team/game context",
    keys=("game_id", "team_id", "athlete_id", "category", "stat_type"),
    order_by=(
        "season",
        "week",
        "game_id",
        "team_ordinal",
        "category_ordinal",
        "stat_type_ordinal",
        "athlete_ordinal",
    ),
    partition_by=("season",),
    event_time="start_date",
)
def player_game_stats(
    *,
    year: int | None = None,
    week: int | None = None,
    season_type: SeasonType | None = None,
    team: str | None = None,
    conference: str | None = None,
    category: str | None = None,
    game_id: int | None = None,
    classification: Classification | None = None,
) -> RecipeRef[list[PlayerGameStat]]:
    """Build long-form player-game statistic observations.

    :param year: Season year used for grouped retrieval.
    :param week: Optional season week.
    :param season_type: Optional season phase.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    :param category: Optional source statistic-category selector.
    :param game_id: Optional exact game identifier.
    :param classification: Optional classification selector.
    :return: A reference to the validated long-form dataset.
    """
    summaries = game_summaries(
        year=year,
        week=week,
        season_type=season_type,
        team=team,
        conference=conference,
        classification=classification,
        game_id=game_id,
    )
    nested = player_game_stats_source(
        year=year,
        week=week,
        season_type=season_type,
        team=team,
        conference=conference,
        category=category,
        game_id=game_id,
        classification=classification,
    )
    return flatten_player_game_stats(summaries, nested)


__all__ = ["PlayerGameStat", "player_game_stats"]
