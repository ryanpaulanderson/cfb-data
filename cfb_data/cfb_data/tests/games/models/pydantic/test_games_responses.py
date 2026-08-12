"""Contract tests for responses documented by the current CFBD API."""

from cfb_data.games.models.pydantic.responses import (
    AdvancedBoxScore,
    CalendarWeek,
    Game,
    GameMedia,
    GameWeather,
    PlayerGameStats,
    ScoreboardGame,
    TeamGameStats,
    TeamRecords,
)


def quarter_stats(total: float = 1.0) -> dict[str, float | None]:
    """Return one complete documented quarter-stat object."""
    return {
        "total": total,
        "quarter1": total,
        "quarter2": None,
        "quarter3": None,
        "quarter4": None,
    }


def test_games_response_matches_current_contract() -> None:
    """Validate all fields currently returned by ``GET /games``."""
    game = Game.model_validate(
        {
            "id": 401628347,
            "season": 2024,
            "week": 1,
            "seasonType": "regular",
            "startDate": "2024-08-31T23:30:00Z",
            "startTimeTBD": False,
            "completed": True,
            "neutralSite": False,
            "conferenceGame": False,
            "attendance": 100077,
            "venueId": 365,
            "venue": "Bryant-Denny Stadium",
            "homeId": 333,
            "homeTeam": "Alabama",
            "homeConference": "SEC",
            "homeClassification": "fbs",
            "homePoints": 63,
            "homeLineScores": [14, 28, 7, 14],
            "homePostgameWinProbability": 0.999,
            "homePregameElo": 1900,
            "homePostgameElo": 1912,
            "awayId": 2459,
            "awayTeam": "Western Kentucky",
            "awayConference": "Conference USA",
            "awayClassification": "fbs",
            "awayPoints": 0,
            "awayLineScores": [0, 0, 0, 0],
            "awayPostgameWinProbability": 0.001,
            "awayPregameElo": 1400,
            "awayPostgameElo": 1388,
            "excitementIndex": 0.42,
            "highlights": "https://www.youtube.com/watch?v=example",
            "notes": None,
            "playoff": {
                "competition": "cfp",
                "format": "12-team",
                "round": "first_round",
                "roundName": "First Round",
                "bracketSlot": "R1-1",
                "homeSeed": 5,
                "awaySeed": 12,
                "bowlName": None,
            },
        }
    )

    assert game.home_postgame_win_probability == 0.999
    assert game.playoff is not None
    assert game.playoff.bracket_slot == "R1-1"


def test_calendar_media_weather_and_records_match_current_contracts() -> None:
    """Validate the four simple games-related response contracts."""
    calendar = CalendarWeek.model_validate(
        {
            "season": 2024,
            "week": 1,
            "seasonType": "regular",
            "startDate": "2024-08-22T00:00:00Z",
            "endDate": "2024-09-03T00:00:00Z",
            "firstGameStart": "2024-08-22T00:00:00Z",
            "lastGameStart": "2024-09-03T00:00:00Z",
        }
    )
    media = GameMedia.model_validate(
        {
            "id": 401628347,
            "season": 2024,
            "week": 1,
            "seasonType": "regular",
            "startTime": "2024-08-31T23:30:00Z",
            "isStartTimeTBD": False,
            "homeTeam": "Alabama",
            "homeConference": "SEC",
            "awayTeam": "Western Kentucky",
            "awayConference": "Conference USA",
            "mediaType": "tv",
            "outlet": "ESPN",
        }
    )
    weather = GameWeather.model_validate(
        {
            "id": 401628347,
            "season": 2024,
            "week": 1,
            "seasonType": "regular",
            "startTime": "2024-08-31T23:30:00Z",
            "gameIndoors": False,
            "homeTeam": "Alabama",
            "homeConference": "SEC",
            "awayTeam": "Western Kentucky",
            "awayConference": "Conference USA",
            "venueId": 365,
            "venue": "Bryant-Denny Stadium",
            "temperature": 84.0,
            "dewPoint": 70.0,
            "humidity": 58.0,
            "precipitation": 0.0,
            "snowfall": 0.0,
            "windDirection": 180.0,
            "windSpeed": 8.0,
            "pressure": 29.9,
            "weatherConditionCode": 2,
            "weatherCondition": "Partly cloudy",
        }
    )
    records = TeamRecords.model_validate(
        {
            "year": 2024,
            "teamId": 333,
            "team": "Alabama",
            "classification": "fbs",
            "conference": "SEC",
            "division": "West",
            "expectedWins": 9.4,
            "total": {"games": 13, "wins": 9, "losses": 4, "ties": 0},
            "conferenceGames": {"games": 8, "wins": 5, "losses": 3, "ties": 0},
            "homeGames": {"games": 7, "wins": 6, "losses": 1, "ties": 0},
            "awayGames": {"games": 5, "wins": 2, "losses": 3, "ties": 0},
            "neutralSiteGames": {"games": 1, "wins": 1, "losses": 0, "ties": 0},
            "regularSeason": {"games": 12, "wins": 9, "losses": 3, "ties": 0},
            "postseason": {"games": 1, "wins": 0, "losses": 1, "ties": 0},
        }
    )

    assert calendar.week == 1
    assert media.outlet == "ESPN"
    assert weather.weather_condition_code == 2
    assert records.total.wins == 9


def test_scoreboard_response_matches_current_contract(
    scoreboard_response: dict[str, object],
) -> None:
    """Validate every current nested ``GET /scoreboard`` field."""
    scoreboard = ScoreboardGame.model_validate(scoreboard_response)

    assert scoreboard.status.value == "in_progress"
    assert scoreboard.home_team.line_scores == [14, 14, 7]
    assert scoreboard.away_team.win_probability == 0.02
    assert scoreboard.weather.wind_direction == 180.0
    assert scoreboard.betting.over_under == 58.5


def test_team_and_player_game_stats_match_current_nested_contracts() -> None:
    """Validate the nested box-score structures used by the current API."""
    team_stats = TeamGameStats.model_validate(
        {
            "id": 401628347,
            "teams": [
                {
                    "teamId": 333,
                    "team": "Alabama",
                    "conference": "SEC",
                    "homeAway": "home",
                    "points": 63,
                    "stats": [{"category": "totalYards", "stat": "600"}],
                }
            ],
        }
    )
    player_stats = PlayerGameStats.model_validate(
        {
            "id": 401628347,
            "teams": [
                {
                    "team": "Alabama",
                    "conference": "SEC",
                    "homeAway": "home",
                    "points": 63,
                    "categories": [
                        {
                            "name": "passing",
                            "types": [
                                {
                                    "name": "C/ATT",
                                    "athletes": [
                                        {
                                            "id": "4433970",
                                            "name": "Jalen Milroe",
                                            "stat": "7/9",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )

    assert team_stats.teams[0].stats[0].stat == "600"
    assert player_stats.teams[0].categories[0].types[0].athletes[0].id == "4433970"


def test_advanced_box_score_matches_current_nested_contract() -> None:
    """Validate every nested section of ``GET /game/box/advanced``."""
    quarter = quarter_stats()
    player_quarter = {**quarter, "rushing": 0.4, "passing": 0.6}
    team_ppa = {
        "team": "Alabama",
        "plays": 60,
        "overall": quarter,
        "passing": quarter,
        "rushing": quarter,
    }
    advanced = AdvancedBoxScore.model_validate(
        {
            "gameInfo": {
                "homeTeam": "Alabama",
                "homePoints": 63,
                "homeWinProb": 0.999,
                "awayTeam": "Western Kentucky",
                "awayPoints": 0,
                "awayWinProb": 0.001,
                "homeWinner": True,
                "excitement": 0.42,
            },
            "teams": {
                "ppa": [team_ppa],
                "cumulativePpa": [team_ppa],
                "successRates": [
                    {
                        "team": "Alabama",
                        "overall": quarter,
                        "standardDowns": quarter,
                        "passingDowns": quarter,
                    }
                ],
                "explosiveness": [{"team": "Alabama", "overall": quarter}],
                "rushing": [
                    {
                        "team": "Alabama",
                        "powerSuccess": 1.0,
                        "stuffRate": 0.1,
                        "lineYards": 150.0,
                        "lineYardsAverage": 3.0,
                        "secondLevelYards": 60.0,
                        "secondLevelYardsAverage": 1.2,
                        "openFieldYards": 30.0,
                        "openFieldYardsAverage": 0.6,
                    }
                ],
                "havoc": [
                    {"team": "Alabama", "total": 0.2, "frontSeven": 0.15, "db": 0.05}
                ],
                "scoringOpportunities": [
                    {
                        "team": "Alabama",
                        "opportunities": 8,
                        "points": 48,
                        "pointsPerOpportunity": 6.0,
                    }
                ],
                "fieldPosition": [
                    {
                        "team": "Alabama",
                        "averageStart": 72.0,
                        "averageStartingPredictedPoints": 1.4,
                    }
                ],
            },
            "players": {
                "usage": [
                    {
                        "player": "Jalen Milroe",
                        "team": "Alabama",
                        "position": "QB",
                        **player_quarter,
                    }
                ],
                "ppa": [
                    {
                        "player": "Jalen Milroe",
                        "team": "Alabama",
                        "position": "QB",
                        "average": player_quarter,
                        "cumulative": player_quarter,
                    }
                ],
            },
        }
    )

    assert advanced.game_info.home_winner
    assert advanced.teams.havoc[0].defensive_back == 0.05
    assert advanced.players.ppa[0].average.passing == 0.6
