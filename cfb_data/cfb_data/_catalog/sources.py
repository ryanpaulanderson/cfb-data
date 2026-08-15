"""Define typed endpoint capabilities for identity-producing API routes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Final

from cfb_data._catalog.projection import runtime_projection_contract_digest


@dataclass(frozen=True, slots=True)
class IdentitySourceSpec:
    """Describe catalog guarantees made by one public response source."""

    endpoint: str
    namespace: str
    capabilities: tuple[str, ...]
    known_cap: int | None = None
    hydration_capability: str | None = None
    contract_version: int = 1

    @property
    def contract_digest(self) -> str:
        """Return a stable digest of this source's catalog contract."""
        payload = json.dumps(
            {
                "endpoint": self.endpoint,
                "namespace": self.namespace,
                "capabilities": self.capabilities,
                "known_cap": self.known_cap,
                "hydration_capability": self.hydration_capability,
                "version": self.contract_version,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"identity-source:v1:{hashlib.sha256(payload.encode()).hexdigest()}"


def _source(
    endpoint: str,
    namespace: str,
    *capabilities: str,
    known_cap: int | None = None,
    hydration_capability: str | None = None,
) -> IdentitySourceSpec:
    """Build one immutable source specification."""
    if hydration_capability is not None and hydration_capability not in capabilities:
        raise ValueError(
            f"Hydration capability {hydration_capability!r} is not produced by {endpoint}"
        )
    return IdentitySourceSpec(
        endpoint=endpoint,
        namespace=namespace,
        capabilities=capabilities,
        known_cap=known_cap,
        hydration_capability=hydration_capability,
    )


IDENTITY_SOURCES: Final[dict[str, IdentitySourceSpec]] = {
    spec.endpoint: spec
    for spec in (
        _source(
            "/teams",
            "team",
            "team.core_identity",
            "team.aliases",
            hydration_capability="team.core_identity",
        ),
        _source(
            "/teams/fbs",
            "team",
            "team.core_identity",
            hydration_capability="team.core_identity",
        ),
        _source(
            "/venues",
            "venue",
            "venue.identity",
            hydration_capability="venue.identity",
        ),
        _source(
            "/conferences",
            "conference",
            "conference.identity",
            hydration_capability="conference.identity",
        ),
        _source(
            "/conferences/affiliations",
            "team",
            "team.conference_history",
            hydration_capability="team.conference_history",
        ),
        _source(
            "/games",
            "game",
            "game.identity",
            "game.schedule",
            "game.team_relationships",
            hydration_capability="game.identity",
        ),
        _source(
            "/roster",
            "athlete",
            "athlete.identity",
            "athlete.team_season",
            "recruit.link",
            hydration_capability="athlete.identity",
        ),
        _source(
            "/player/search",
            "athlete",
            "athlete.identity",
            "athlete.team_season",
            known_cap=100,
        ),
        _source(
            "/plays/types",
            "play_type",
            "play_type.identity",
            hydration_capability="play_type.identity",
        ),
        _source(
            "/plays/stats/types",
            "play_stat_type",
            "play_stat_type.identity",
            hydration_capability="play_stat_type.identity",
        ),
        _source(
            "/stats/categories",
            "stat_category",
            "stat_category.identity",
            hydration_capability="stat_category.identity",
        ),
        _source(
            "/conferences/changes",
            "team",
            "team.core_identity",
            "team.conference_history",
        ),
        _source("/teams/ats", "team", "team.core_identity"),
        _source("/records", "team", "team.core_identity"),
        _source("/rankings", "team", "team.core_identity"),
        _source("/wepa/team/season", "team", "team.core_identity"),
        _source("/games/media", "game", "game.identity"),
        _source(
            "/games/weather",
            "game",
            "game.identity",
            "game.venue_relationship",
        ),
        _source(
            "/games/teams",
            "game",
            "game.identity",
            "game.team_relationships",
        ),
        _source(
            "/games/players",
            "game",
            "game.identity",
            "athlete.identity",
            "athlete.team_season",
        ),
        _source(
            "/scoreboard",
            "game",
            "game.identity",
            "game.team_relationships",
        ),
        _source("/lines", "game", "game.identity", "game.team_relationships"),
        _source(
            "/metrics/wp",
            "play",
            "game.identity",
            "play.identity",
            "game.team_relationships",
        ),
        _source("/metrics/wp/pregame", "game", "game.identity"),
        _source("/ppa/games", "game", "game.identity"),
        _source("/stats/game/advanced", "game", "game.identity"),
        _source("/stats/game/havoc", "game", "game.identity"),
        _source(
            "/stats/player/success/game",
            "athlete",
            "athlete.identity",
            "athlete.team_season",
            "game.identity",
        ),
        _source(
            "/plays",
            "play",
            "play.identity",
            "play.game_relationship",
            "drive.identity",
        ),
        _source(
            "/plays/stats",
            "play",
            "play.identity",
            "drive.identity",
            "athlete.identity",
            "athlete.team_season",
        ),
        _source(
            "/drives",
            "drive",
            "drive.identity",
            "drive.game_relationship",
            "team.core_identity",
        ),
        _source(
            "/live/plays",
            "game",
            "game.identity",
            "game.team_relationships",
            "drive.identity",
            "play.identity",
            "team.core_identity",
            "play_type.identity",
        ),
        *(
            _source(
                endpoint,
                "athlete",
                "athlete.identity",
                "athlete.team_season",
            )
            for endpoint in (
                "/player/usage",
                "/player/season/overview",
                "/player/returning",
                "/stats/player/season",
                "/stats/player/success",
                "/ppa/players/games",
                "/ppa/players/season",
                "/wepa/players/passing",
                "/wepa/players/rushing",
                "/wepa/players/kicking",
            )
        ),
        _source(
            "/recruiting/players",
            "recruit",
            "recruit.identity",
            "recruit.athlete_link",
        ),
        _source("/coaches", "coach", "coach.identity", "coach.team_season"),
        _source("/coaches/profile", "coach", "coach.identity"),
        _source("/coaches/seasons", "coach", "coach.identity", "coach.team_season"),
        _source("/coaches/tenures", "coach", "coach.identity", "coach.tenure"),
        _source(
            "/draft/picks",
            "draft",
            "athlete.identity",
            "team.core_identity",
            "draft.identity",
        ),
        _source("/draft/teams", "draft_team", "draft_team.identity"),
        _source("/draft/positions", "draft_position", "draft_position.identity"),
        _source(
            "/playoffs/cfp",
            "playoff",
            "playoff.matchup",
            "game.identity",
            "team.core_identity",
        ),
        _source(
            "/playoffs/cfp/games",
            "playoff",
            "playoff.matchup",
            "game.identity",
            "team.core_identity",
        ),
        _source("/playoffs/cfp/participants", "playoff", "team.core_identity"),
    )
}


def identity_source(endpoint: str) -> IdentitySourceSpec:
    """Return the source specification or an identity-neutral default."""
    return IDENTITY_SOURCES.get(
        endpoint,
        IdentitySourceSpec(
            endpoint=endpoint,
            namespace=endpoint.strip("/").replace("/", "."),
            capabilities=(),
        ),
    )


def projection_contract(endpoint: str) -> str:
    """Return the current endpoint and source-declaration contract digest."""
    return (
        f"{identity_source(endpoint).contract_digest}:"
        f"{runtime_projection_contract_digest()}"
    )
