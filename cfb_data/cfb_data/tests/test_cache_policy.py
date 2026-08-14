"""Test endpoint profiles and response-state cache policy refinements."""

from datetime import UTC, datetime, timedelta

from cfb_data.cache.config import CachePolicyConfig, CacheProfile, CacheTTL
from cfb_data.cache.policy import cache_profile, resolve_ttl
from cfb_data.games.models.pydantic.responses import Game


def test_cache_profiles_cover_operational_live_and_domain_cadences() -> None:
    """Map representative endpoints to their semantic policy owners."""
    assert cache_profile("/info/usage") is CacheProfile.operational
    assert cache_profile("/teams") is CacheProfile.stable_reference
    assert cache_profile("/plays/types") is CacheProfile.reference_vocabulary
    assert cache_profile("/roster") is CacheProfile.roster
    assert cache_profile("/games") is CacheProfile.schedule
    assert cache_profile("/scoreboard") is CacheProfile.live_scoreboard
    assert cache_profile("/live/plays") is CacheProfile.live_plays
    assert cache_profile("/games/weather") is CacheProfile.weather
    assert cache_profile("/lines") is CacheProfile.betting
    assert cache_profile("/recruiting/players") is CacheProfile.recruiting
    assert cache_profile("/rankings") is CacheProfile.active_season


def test_empty_current_partition_is_fresh_for_at_most_one_day() -> None:
    """Avoid retaining not-yet-published empty data beyond one day."""
    ttl = resolve_ttl(
        profile=CacheProfile.roster,
        endpoint="/roster",
        parameters={"year": 2026},
        value=[],
        policy=CachePolicyConfig(),
        now=datetime(2026, 8, 13, tzinfo=UTC),
    )

    assert ttl == CacheTTL(timedelta(days=1), timedelta(days=30))


def test_empty_closed_partition_uses_historical_policy() -> None:
    """Retain an empty partition after its requested season is definitively closed."""
    ttl = resolve_ttl(
        profile=CacheProfile.roster,
        endpoint="/roster",
        parameters={"year": 2024},
        value=[],
        policy=CachePolicyConfig(),
        now=datetime(2026, 8, 13, tzinfo=UTC),
    )

    assert ttl == CacheTTL(timedelta(days=365), timedelta(days=1825))


def test_closed_games_use_historical_policy_and_user_override(
    game_response: dict[str, object],
) -> None:
    """Promote only completed games beyond the correction window to historical."""
    game = Game.model_validate(game_response)
    override = CacheTTL(timedelta(days=400), timedelta(days=2000))
    ttl = resolve_ttl(
        profile=CacheProfile.schedule,
        endpoint="/games",
        parameters={"year": 2024},
        value=[game],
        policy=CachePolicyConfig({CacheProfile.historical: override}),
        now=datetime(2026, 8, 13, tzinfo=UTC),
    )

    assert ttl == override


def test_imminent_and_recent_games_use_shortest_applicable_policy(
    game_response: dict[str, object],
) -> None:
    """Apply 24-hour freshness around kickoff and the correction window."""
    now = datetime(2026, 8, 13, tzinfo=UTC)
    game = Game.model_validate(game_response)
    imminent = game.model_copy(
        update={"completed": False, "start_date": now + timedelta(hours=12)}
    )
    recent = game.model_copy(
        update={"completed": True, "start_date": now - timedelta(hours=12)}
    )

    imminent_ttl = resolve_ttl(
        profile=CacheProfile.schedule,
        endpoint="/games",
        parameters={"id": game.id},
        value=[imminent],
        policy=CachePolicyConfig(),
        now=now,
    )
    recent_ttl = resolve_ttl(
        profile=CacheProfile.schedule,
        endpoint="/games",
        parameters={"id": game.id},
        value=[recent],
        policy=CachePolicyConfig(),
        now=now,
    )

    assert imminent_ttl == CacheTTL(timedelta(hours=24), timedelta(days=7))
    assert recent_ttl == CacheTTL(timedelta(hours=24), timedelta(days=30))


def test_mixed_game_policy_is_independent_of_response_order(
    game_response: dict[str, object],
) -> None:
    """Choose the shortest complete policy for every response ordering."""
    now = datetime(2026, 8, 13, tzinfo=UTC)
    game = Game.model_validate(game_response)
    imminent = game.model_copy(
        update={"completed": False, "start_date": now + timedelta(hours=12)}
    )
    recent = game.model_copy(
        update={"completed": True, "start_date": now - timedelta(hours=12)}
    )
    expected = CacheTTL(timedelta(hours=24), timedelta(days=7))

    for rows in ([imminent, recent], [recent, imminent]):
        assert (
            resolve_ttl(
                profile=CacheProfile.schedule,
                endpoint="/games",
                parameters={"year": 2026},
                value=rows,
                policy=CachePolicyConfig(),
                now=now,
            )
            == expected
        )
