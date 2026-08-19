"""Generate the local recipe demonstration snapshot from validated artifacts."""

from __future__ import annotations

import asyncio
import json
import math
import os
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from cfb_data.analytics import AnalyticsConfig, RecipeRun, WorkflowOutputs
from cfb_data.tests._live_budget import LiveCallLedger
from cfb_data_recipes.program_history import program_history
from cfb_data_recipes.single_game_analysis import single_game_analysis
from cfb_data_recipes.team_seasons import team_seasons
from pydantic import ConfigDict, TypeAdapter

from cfb_data import CFBDClient, RedisCacheConfig, RetryPolicy

_REPOSITORY_ROOT = Path(__file__).parents[3]
_REPORT_PATH = _REPOSITORY_ROOT / ".cfb-data-live/live-analytics-report.json"
_LEDGER_PATH = _REPOSITORY_ROOT / ".cfb-data-live/call-ledger.json"
_OUTPUT_PATH = Path(__file__).parents[1] / "app/data.json"
_REDIS_URL = "redis://127.0.0.1:6379/0"
_REDIS_PREFIX = "cfb-data:penn-state-atlas"
_TEAM = "Penn State"
_SEASON = 2024
_GAME_ID = 401628515
_INTEGER = TypeAdapter(int, config=ConfigDict(strict=True))
_FLOAT = TypeAdapter(float)


async def _generate() -> dict[str, object]:
    """Return a bounded website snapshot using only local cached retrievals."""
    api_key = os.getenv("CFBD_API_KEY")
    if not api_key:
        raise RuntimeError("CFBD_API_KEY is required to address its Redis scope")
    ledger = LiveCallLedger(_LEDGER_PATH)
    initial_spent = ledger.snapshot().spent
    with tempfile.TemporaryDirectory(prefix="cfb-data-site-") as directory:
        async with CFBDClient(
            api_key,
            cache=RedisCacheConfig(
                url=_REDIS_URL,
                key_prefix=_REDIS_PREFIX,
            ),
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=Path(directory)),
        ) as client:
            with client.cache_mode("local_only"):
                season: RecipeRun[pd.DataFrame] = await team_seasons.run(
                    client,
                    season=_SEASON,
                    team=_TEAM,
                )
                game: RecipeRun[
                    WorkflowOutputs[pd.DataFrame]
                ] = await single_game_analysis.run(client, game_id=_GAME_ID)
                history: RecipeRun[
                    WorkflowOutputs[pd.DataFrame]
                ] = await program_history.run(
                    client,
                    team=_TEAM,
                    start_season=_SEASON,
                    end_season=_SEASON,
                )
    final_spent = ledger.snapshot().spent
    if final_spent != initial_spent:
        raise RuntimeError("Local-only website generation consumed an API attempt")
    report: object = json.loads(_REPORT_PATH.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("status") != "passed":
        raise RuntimeError("A passing redacted live analytics report is required")
    return {
        "generatedAt": datetime.now(UTC).isoformat(),
        "sourceMode": "Redis local_only",
        "ledgerBefore": initial_spent,
        "ledgerAfter": final_spent,
        "season": _season_evidence(season.value, history.value),
        "game": _game_evidence(game.value),
        "runtime": _runtime_evidence(report),
    }


def _season_evidence(
    season_frame: pd.DataFrame,
    history: WorkflowOutputs[pd.DataFrame],
) -> dict[str, object]:
    """Derive one reader-facing season summary after recipe validation."""
    if len(season_frame) != 1:
        raise RuntimeError("Expected one Penn State season row")
    season = season_frame.iloc[0]
    total = _mapping(season["total"])
    conference = _mapping(season["conference_games"])
    home = _mapping(season["home_games"])
    away = _mapping(season["away_games"])
    postseason = _mapping(season["postseason"])
    team_games = history["team_games"]
    perspectives = team_games.loc[team_games["team_id"] == int(season["team_id"])]
    perspectives = perspectives.sort_values("start_date", kind="stable")
    schedule = [
        {
            "gameId": int(row.game_id),
            "week": int(row.week),
            "seasonType": str(row.season_type),
            "opponent": str(row.opponent),
            "site": str(row.home_away),
            "result": str(row.result).upper(),
            "pointsFor": int(row.points),
            "pointsAgainst": int(row.opponent_points),
            "differential": int(row.point_differential),
        }
        for row in perspectives.itertuples(index=False)
    ]
    coach = history["coach_seasons"].iloc[0]
    scoring = _mapping(coach["scoring"])
    poll_resume = _mapping(coach["poll_resume"])
    recruiting = history["recruiting_classes"].iloc[0]
    recruits = recruiting["recruits"]
    if not isinstance(recruits, list):
        raise RuntimeError("Recruiting rows must preserve ordered recruit records")
    top_recruits = [
        {
            "name": str(_mapping(recruit)["name"]),
            "position": str(_mapping(recruit)["position"]),
            "stars": _integer(_mapping(recruit)["stars"]),
            "rating": _floating(_mapping(recruit)["rating"]),
            "nationalRank": _integer(_mapping(recruit)["ranking"]),
        }
        for recruit in recruits[:5]
    ]
    return {
        "team": str(season["team"]),
        "season": int(season["season"]),
        "conference": str(season["conference"]),
        "record": f"{_integer(total['wins'])}-{_integer(total['losses'])}",
        "wins": _integer(total["wins"]),
        "losses": _integer(total["losses"]),
        "expectedWins": round(float(season["expected_wins"]), 1),
        "conferenceRecord": (
            f"{_integer(conference['wins'])}-{_integer(conference['losses'])}"
        ),
        "homeRecord": f"{_integer(home['wins'])}-{_integer(home['losses'])}",
        "awayRecord": f"{_integer(away['wins'])}-{_integer(away['losses'])}",
        "postseasonRecord": (
            f"{_integer(postseason['wins'])}-{_integer(postseason['losses'])}"
        ),
        "pointsFor": _integer(scoring["points_for"]),
        "pointsAgainst": _integer(scoring["points_against"]),
        "averagePointDifferential": round(
            _floating(scoring["average_point_differential"]),
            1,
        ),
        "coach": f"{coach['coach_first_name']} {coach['coach_last_name']}",
        "preseasonRank": int(coach["preseason_rank"]),
        "postseasonRank": int(coach["postseason_rank"]),
        "bestRank": _integer(poll_resume["best_rank"]),
        "weeksTopTen": _integer(poll_resume["weeks_top_ten"]),
        "recruitingRank": int(recruiting["rank"]),
        "recruitCount": int(recruiting["recruit_count"]),
        "topRecruits": top_recruits,
        "schedule": schedule,
    }


def _game_evidence(outputs: WorkflowOutputs[pd.DataFrame]) -> dict[str, object]:
    """Derive one game story from six validated workflow outputs."""
    summary = outputs["game_summaries"].iloc[0]
    plays = outputs["plays"]
    drives = outputs["drives"]
    player_stats = outputs["player_game_stats"]
    lines = outputs["betting_lines"]
    ppa_observed = plays.loc[plays["ppa"].notna()]
    explosive = ppa_observed.loc[ppa_observed["yards_gained"] >= 20]
    team_breakdown: list[dict[str, object]] = []
    for team in (str(summary["home_team"]), str(summary["away_team"])):
        team_plays = ppa_observed.loc[ppa_observed["offense"] == team]
        team_drives = drives.loc[drives["offense"] == team]
        team_breakdown.append(
            {
                "team": team,
                "ppaObservedPlays": int(len(team_plays)),
                "scoringDrives": int(team_drives["scoring"].sum()),
                "explosivePlays": int(
                    len(team_plays.loc[team_plays["yards_gained"] >= 20])
                ),
                "averagePpa": round(float(team_plays["ppa"].mean()), 3),
            }
        )
    biggest = explosive.sort_values(
        ["yards_gained", "play_number"],
        ascending=[False, True],
        kind="stable",
    ).head(5)
    big_plays = [
        {
            "offense": str(row.offense),
            "period": int(row.period),
            "yards": int(row.yards_gained),
            "type": str(row.play_type),
            "text": str(row.play_text),
            "ppa": None if _missing(row.ppa) else round(float(row.ppa), 3),
        }
        for row in biggest.itertuples(index=False)
    ]
    market = [
        {
            "provider": str(row.provider),
            "spread": str(row.formatted_spread),
            "openSpread": None if _missing(row.spread_open) else float(row.spread_open),
            "total": None if _missing(row.over_under) else float(row.over_under),
            "openTotal": None
            if _missing(row.over_under_open)
            else float(row.over_under_open),
        }
        for row in lines.itertuples(index=False)
    ]
    return {
        "gameId": int(summary["game_id"]),
        "season": int(summary["season"]),
        "week": int(summary["week"]),
        "venue": str(summary["venue"]),
        "homeTeam": str(summary["home_team"]),
        "homePoints": int(summary["home_points"]),
        "awayTeam": str(summary["away_team"]),
        "awayPoints": int(summary["away_points"]),
        "margin": int(summary["margin"]),
        "totalPoints": int(summary["total_points"]),
        "excitementIndex": round(float(summary["excitement_index"]), 2),
        "playCount": int(len(plays)),
        "ppaObservedPlayCount": int(len(ppa_observed)),
        "driveCount": int(len(drives)),
        "scoringDriveCount": int(drives["scoring"].sum()),
        "explosivePlayCount": int(len(explosive)),
        "playerObservationCount": int(len(player_stats)),
        "athleteCount": int(player_stats["athlete_id"].nunique()),
        "teams": team_breakdown,
        "bigPlays": big_plays,
        "market": market,
        "workflowOutputs": list(outputs),
    }


def _runtime_evidence(report: Mapping[str, object]) -> dict[str, object]:
    """Project the redacted live report into reader-facing runtime evidence."""
    parity = _mapping(report["parity"])
    parity_rows: list[dict[str, object]] = []
    for option, raw in sorted(parity.items()):
        evidence = _mapping(raw)
        retrieval = _mapping(_mapping(evidence["retrieval"])["totals"])
        parity_rows.append(
            {
                "option": option,
                "httpAttempts": _integer(retrieval["http_attempts"]),
                "daskNodes": _integer(evidence["dask_nodes"]),
                "canonicalMatch": True,
            }
        )
    checkpoint = _mapping(report["checkpoint_replay"])
    recovery = _mapping(report["recovery"])
    fresh = _mapping(report["fresh_run"])
    return {
        "plannedRecipes": len(_mapping(report["plans"])),
        "sourceCandidates": _integer(report["source_candidates"]),
        "plannedWorstCaseAttempts": _integer(report["planned_worst_case_attempts"]),
        "actualAttempts": _integer(report["attempt_delta"]),
        "parity": parity_rows,
        "checkpointDaskStarts": _integer(checkpoint["second_run_dask_starts"]),
        "recoveryReusedNodes": _integer(recovery["reused_nodes"]),
        "recoveryHttpAttempts": _integer(recovery["actual_http_attempts"]),
        "freshRunHttpAttempts": _integer(fresh["actual_http_attempts"]),
    }


def _mapping(value: object) -> Mapping[str, object]:
    """Narrow one validated nested record to a string-keyed mapping."""
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise RuntimeError("Expected a string-keyed analytical record")
    return value


def _integer(value: object) -> int:
    """Return one strictly validated integer from nested analytical evidence."""
    return _INTEGER.validate_python(value)


def _floating(value: object) -> float:
    """Return one finite float from nested analytical evidence."""
    result = _FLOAT.validate_python(value)
    if not math.isfinite(result):
        raise RuntimeError("Expected a finite analytical number")
    return result


def _missing(value: object) -> bool:
    """Return whether a scalar is an explicit analytical missing value."""
    if value is None:
        return True
    if isinstance(value, float):
        return not math.isfinite(value)
    result = pd.isna(value)
    return bool(result) if isinstance(result, bool) else False


def main() -> None:
    """Write one deterministic bounded JSON snapshot for the local website."""
    snapshot = asyncio.run(_generate())
    encoded = json.dumps(snapshot, indent=2, sort_keys=True, allow_nan=False) + "\n"
    temporary = _OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(_OUTPUT_PATH)
    print(f"wrote {_OUTPUT_PATH.relative_to(_REPOSITORY_ROOT)} without API attempts")


if __name__ == "__main__":
    main()
