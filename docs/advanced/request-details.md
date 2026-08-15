# Advanced request details

This page collects exact enum values and recurring validation rules. Start with
[Requests and allowed values](../guides/requests.md) for ordinary calls.

## Shared enum values

Enum fields accept either the exported member or its exact string value.
Strings are case-sensitive.

| Enum | Accepted strings | Used for |
| --- | --- | --- |
| {class}`cfb_data.SeasonType` | `regular`, `postseason`, `both`, `allstar`, `spring_regular`, `spring_postseason` | Season phase |
| {class}`cfb_data.Classification` | `fbs`, `fcs`, `ii`, `iii` | Division classification |
| {class}`cfb_data.ConferenceClassification` | `fbs`, `fcs`, `ii`, `ii/iii`, `iii` | Conference responses and filters |
| {class}`cfb_data.MediaType` | `tv`, `radio`, `web`, `ppv`, `mobile` | Broadcast medium |
| {class}`cfb_data.RankingPoll` | `cfp` | Poll snapshot selector |
| {class}`cfb_data.RecruitClassification` | `JUCO`, `PrepSchool`, `HighSchool` | Recruiting source classification |
| {class}`cfb_data.PlayoffCompetition` | `cfp` | Playoff competition |
| {class}`cfb_data.PlayoffRound` | `first_round`, `quarterfinal`, `semifinal`, `championship` | CFP round |
| {class}`cfb_data.UserUsageApi` | `all`, `cfb`, `cbb` | Account usage product |

{class}`cfb_data.TransferEligibility` describes response values:
`Withdrawn`, `TBD`, `PendingAppeal`, `SittingOne`, and `Immediate`.

The season-specific reference catalog is exposed as
{class}`cfb_data.TeamName` and {class}`cfb_data.ConferenceName`, with the
ergonomic aliases `teams` and `conferences` in {mod}`cfb_data.enums`. The
snapshot season is {data}`cfb_data.enums.REFERENCE_SEASON`; historical values
outside that snapshot remain valid ordinary strings.

Live-play response enums use:

- `home` or `away` for {class}`cfb_data.HomeAway`;
- `rush`, `pass`, or `other` for {class}`cfb_data.RushPass`; and
- `passing` or `standard` for {class}`cfb_data.DownType`.

These are response values rather than general request filters.

## Recurring validation rules

Endpoint-specific requirements are listed in the [endpoint
reference](../cfbd_api/README.md). Across namespaces, these rules recur:

- Season years generally start at 1869. Draft years start at 1936 and CFP
  seasons at 2014. There is no fixed future-year cap.
- IDs are positive integers; weeks and similar counters are non-negative.
- Text filters declared as non-empty reject empty strings.
- A lower bound such as `min_year`, `start_year`, or `start_week` cannot exceed
  its corresponding upper bound.
- Some endpoints require one selector from a group, such as `year` or `team`.
  Game-stat endpoints accept a `game_id` or a grouped season selector.
- CFP `round` requires `competition="cfp"`, and CFP competition pairs only with
  postseason-compatible season types.
- Rankings `latest` and `final` snapshots require `poll="cfp"` and cannot both
  be true.

## Python and upstream field names

Python calls use snake case, such as `season_type`, `media_type`, and
`game_id`. Request models serialize the upstream spelling (`seasonType`,
`mediaType`, `gameId`, or `id`) automatically.

Extra fields are rejected, which catches misspellings before an API call. The
generated [request model reference](../reference/requests.rst) lists every
class, field type, default, and docstring.
