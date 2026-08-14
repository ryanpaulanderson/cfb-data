"""Define the exhaustive opt-in public REST route manifest."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class LiveEndpointCase:
    """Name one public resource method and its exact REST route."""

    endpoint: str
    resource: str
    method: str


LIVE_ENDPOINT_CASES: Final[tuple[LiveEndpointCase, ...]] = (
    LiveEndpointCase("/teams", "teams", "list"),
    LiveEndpointCase("/teams/fbs", "teams", "fbs"),
    LiveEndpointCase("/conferences", "conferences", "list"),
    LiveEndpointCase("/venues", "venues", "list"),
    LiveEndpointCase("/games", "games", "list"),
    LiveEndpointCase("/scoreboard", "games", "scoreboard"),
    LiveEndpointCase("/roster", "teams", "roster"),
    LiveEndpointCase("/coaches", "coaches", "list"),
    LiveEndpointCase("/info", "info", "account"),
    LiveEndpointCase("/info/usage", "info", "usage"),
    LiveEndpointCase("/calendar", "games", "calendar"),
    LiveEndpointCase("/coaches/profile", "coaches", "profile"),
    LiveEndpointCase("/coaches/seasons", "coaches", "seasons"),
    LiveEndpointCase("/coaches/tenures", "coaches", "tenures"),
    LiveEndpointCase("/conferences/affiliations", "conferences", "affiliations"),
    LiveEndpointCase("/conferences/changes", "conferences", "changes"),
    LiveEndpointCase("/draft/picks", "draft", "picks"),
    LiveEndpointCase("/draft/positions", "draft", "positions"),
    LiveEndpointCase("/draft/teams", "draft", "teams"),
    LiveEndpointCase("/drives", "drives", "list"),
    LiveEndpointCase("/game/box/advanced", "games", "advanced_box_score"),
    LiveEndpointCase("/games/media", "games", "media"),
    LiveEndpointCase("/games/players", "games", "player_stats"),
    LiveEndpointCase("/games/teams", "games", "team_stats"),
    LiveEndpointCase("/games/weather", "games", "weather"),
    LiveEndpointCase("/lines", "betting", "lines"),
    LiveEndpointCase("/live/plays", "plays", "live"),
    LiveEndpointCase("/metrics/fg/ep", "metrics", "field_goal_expected_points"),
    LiveEndpointCase("/metrics/wp", "metrics", "win_probability"),
    LiveEndpointCase("/metrics/wp/pregame", "metrics", "pregame_win_probability"),
    LiveEndpointCase("/player/portal", "players", "transfer_portal"),
    LiveEndpointCase("/player/returning", "players", "returning_production"),
    LiveEndpointCase("/player/search", "players", "search"),
    LiveEndpointCase("/player/season/overview", "players", "season_overview"),
    LiveEndpointCase("/player/usage", "players", "usage"),
    LiveEndpointCase("/playoffs/cfp", "playoffs", "cfp"),
    LiveEndpointCase("/playoffs/cfp/games", "playoffs", "games"),
    LiveEndpointCase("/playoffs/cfp/participants", "playoffs", "participants"),
    LiveEndpointCase("/plays", "plays", "list"),
    LiveEndpointCase("/plays/stats", "plays", "stats"),
    LiveEndpointCase("/plays/stats/types", "plays", "stat_types"),
    LiveEndpointCase("/plays/types", "plays", "types"),
    LiveEndpointCase("/ppa/games", "metrics", "team_game_ppa"),
    LiveEndpointCase("/ppa/players/games", "metrics", "player_game_ppa"),
    LiveEndpointCase("/ppa/players/season", "metrics", "player_season_ppa"),
    LiveEndpointCase("/ppa/predicted", "metrics", "predicted_points"),
    LiveEndpointCase("/ppa/teams", "metrics", "team_season_ppa"),
    LiveEndpointCase("/rankings", "rankings", "list"),
    LiveEndpointCase("/ratings/core", "ratings", "core"),
    LiveEndpointCase("/ratings/elo", "ratings", "elo"),
    LiveEndpointCase("/ratings/fpi", "ratings", "fpi"),
    LiveEndpointCase("/ratings/sp", "ratings", "sp"),
    LiveEndpointCase("/ratings/sp/conferences", "ratings", "conference_sp"),
    LiveEndpointCase("/ratings/srs", "ratings", "srs"),
    LiveEndpointCase("/ratings/srs/expanded", "ratings", "expanded_srs"),
    LiveEndpointCase("/records", "games", "records"),
    LiveEndpointCase("/recruiting/groups", "recruiting", "groups"),
    LiveEndpointCase("/recruiting/players", "recruiting", "players"),
    LiveEndpointCase("/recruiting/teams", "recruiting", "teams"),
    LiveEndpointCase("/stats/categories", "stats", "categories"),
    LiveEndpointCase("/stats/game/advanced", "stats", "advanced_game"),
    LiveEndpointCase("/stats/game/havoc", "stats", "game_havoc"),
    LiveEndpointCase("/stats/player/season", "stats", "player_season"),
    LiveEndpointCase("/stats/player/success", "stats", "player_season_success"),
    LiveEndpointCase("/stats/player/success/game", "stats", "player_game_success"),
    LiveEndpointCase("/stats/season", "stats", "team_season"),
    LiveEndpointCase("/stats/season/advanced", "stats", "advanced_season"),
    LiveEndpointCase("/talent", "teams", "talent"),
    LiveEndpointCase("/teams/ats", "teams", "ats"),
    LiveEndpointCase("/teams/matchup", "teams", "matchup"),
    LiveEndpointCase("/wepa/players/kicking", "adjusted_metrics", "kicker_paar"),
    LiveEndpointCase("/wepa/players/passing", "adjusted_metrics", "player_passing"),
    LiveEndpointCase("/wepa/players/rushing", "adjusted_metrics", "player_rushing"),
    LiveEndpointCase("/wepa/team/season", "adjusted_metrics", "team_season"),
)
