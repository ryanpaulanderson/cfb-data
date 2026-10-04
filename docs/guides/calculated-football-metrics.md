# Calculate Success Rate and opponent-adjusted Line Yards

These recipes calculate new statistics from `/plays` and `/games`. They never
read upstream success rates, ALY, PPA, EPA, or team ratings. The workflows
return named pandas or Polars tables and durable artifacts through the usual
[recipe interface](modular-analytics.md). Every transformation has a declared
row schema, semantic revision, and visible place in the execution graph.

## Run with Redis

```python
from pathlib import Path

from cfb_data import CFBDClient, RedisCacheConfig
from cfb_data.analytics import AnalyticsConfig, ExecutionPolicy
from cfb_data.enums import Classification
from cfb_data_recipes.line_yards import line_yards
from cfb_data_recipes.success_rate import success_rate


async def calculate() -> None:
    async with CFBDClient(
        cache=RedisCacheConfig(url="redis://127.0.0.1:6379/0"),
        analytics=AnalyticsConfig(root=Path(".analytics")),
    ) as client:
        success = await success_rate(
            client,
            year=2024,
            weeks=tuple(range(1, 9)),
            classification=Classification.fbs,
        )
        adjusted = await line_yards.run(
            client,
            year=2024,
            weeks=tuple(range(1, 9)),
            classification=Classification.fbs,
            policy=ExecutionPolicy(executor="dask", max_http_attempts=30),
        )

    print(success["team_seasons"])
    print(adjusted.value["team_seasons"])
    print(adjusted.value["calibration"])
    print(adjusted.actual_http_attempts, adjusted.reused_nodes)
```

Weeks are explicit, unique partitions (0–32, at most 32); the builder never
discovers additional requests from retrieved data. Unfiltered play types keep
exclusions and unknown classifications observable. Each workflow requests one
season game population and one play source per week. Redis caches those API
responses; SQLite/Parquet analytics checkpoints own intermediate and final
products. Warm source-cache runs can recompute with `checkpoint_mode="off"`.
Use `client.cache_mode("local_only")` to require cached responses without HTTP.

Success Rate's `team` selector limits its source population to that team's
games. ALY's `team` selector filters the final ratings **after** fitting the
entire selected population. An opponent-adjusted fit requires opponents and
their schedules. `classification` and `season_type` define that population;
they are retained in source identity and graph fingerprints.

## Success Rate recipe and math

The rule is 50% of yards to gain on first down, 70% on second, and a first down
on third or fourth. Integer comparisons avoid rounding short-yardage thresholds:

```text
first:   2 * yards_gained >= distance
second: 10 * yards_gained >= 7 * distance
third/fourth: yards_gained >= distance
```

Interceptions fail even when `yards_gained` describes a long return. Explicit
opponent-recovered fumble events also fail when the text establishes a rushing
or passing action. Conflicting action cues, own recoveries, unknown fumble
origins, and ambiguous penalty enforcement remain unknown.
Safety and uncategorized-touchdown records also retain unknown action origins
rather than being mislabeled as outside scrimmage. Fumble-return yards
never become successful offensive gain. Sacks count as dropbacks. Kneels,
spikes, nullified plays, special teams, conversions, incomplete games, and
overtime are excluded from this regulation-only product. Goal-to-go uses the
source's distance; contradictory down/distance/field evidence fails validation.

```text
success_rate = successful_plays / evaluated_plays
eligible_plays = evaluated_plays + unknown_plays
source_rows = evaluated_plays + unknown_plays + excluded_plays
```

Unknowns never become failed plays. A zero evaluated denominator returns null.
`team_games` reports both participants, offense/defense, and all/rush/dropback
splits. `team_seasons` pools numerators and denominators across games rather
than averaging game rates. Defensive rates describe success **allowed**.
Unallocated unknown actions are counted separately and flag affected splits.
Administrative exclusions rely on identifiable recorded text. Splits follow
the source action taxonomy: quarterback scrambles tagged `Rush` stay in the
rush split because the schema does not establish called-play intent.

The named `plays` table is the independently composable
`cfb_data_recipes.scrimmage_plays.scrimmage_plays` dataset. It retains source
ordinals, game and participant IDs, nullable success flags, and specific reasons
for each metric's evaluation decision. Source row order is retained within its
declared week/game ordering. Duplicate play keys or conflicting participants
fail globally, including across partitions.

## College ALY recipe and math

First transform evaluated rush gain `y` into line yards `z`:

```text
y < 0:       z = 1.2 * y
0 <= y <= 4: z = y
4 < y <= 10: z = 4 + 0.5 * (y - 4)
y > 10:      z = 7
```

Our college variant includes all carriers, including quarterbacks. Sacks,
kneels, and fumble events are excluded; unknown rushing/enforcement evidence
stays visible. This is not FTN's running-back-only proprietary implementation.
The metric does not isolate blocking from runner ability.

Fit the following effects simultaneously:

```text
z_i = mu + offense[team_i] - prevention[opponent_i] + context_i + error_i
```

The context uses down × distance × field-position cells (120 possible), quarter,
late-half/ordinary/unknown clock, home/away/neutral venue, and score-margin ×
quarter × clock interactions. Distance bands are 1–2, 3–5, 6–10, 11–15, 16+;
yards-to-goal bands are 1–5, 6–10, 11–20, 21–50, 51–80, 81–99. Score bands
are tied, leading/trailing by 1–7, 8–14, or 15+. Score timing is inferred from
adjacent scoring evidence; unresolved timing has its own `unknown` category.
Formation, box count, direction, personnel, and yards before contact are
unsupported by these sources. No garbage-time or future result flag is used.

Let `X` contain an intercept and signed one-hot effect contributions. With
optional half-life `tau`, `w_i = 2 ** (-age_days_i / tau)`; otherwise weights
are one. Age is relative to the latest admitted training game. Minimize:

```text
(z - X theta)' W (z - X theta) + (theta - p)' Lambda (theta - p)
subject to C theta = 0
```

`Lambda` has an unpenalized intercept, one positive team penalty for offense
and defense, and a context penalty for other blocks. `C` exposure-centers every
non-intercept block, using weighted observations. `p` is zero unless an earlier
season team model is supplied; prior team means are recentered using current
exposures, and new teams receive zero prior means. Context priors remain zero.
The bounded coefficient solve is:

```text
[X' W X + Lambda   C'] [theta] = [X' W z + Lambda p]
[C                 0] [ nu  ]   [        0         ]
```

The normal-equation terms are distributed table reductions. Only these
coefficient-scale statistics cross `Table.collect_bounded`; play rows never
gather for fitting. `max_parameters` defaults to 768 and may be 2–1024. A
larger unsupported coefficient population fails explicitly instead of silently
dropping teams or context. Solve nodes stay on the coordinator; designs,
reductions, predictions, joins, and coverage remain native lazy table graphs.

Normalize fitted team effects using the exact weighted raw rushing-YPC baseline
`YPC` of the training population:

```text
offensive adjusted_line_yards = YPC + offense_effect
defensive adjusted_line_yards = YPC - prevention_effect
```

Better offensive ratings are larger. Better defensive prevention effects are
larger, while better defensive **allowed-yardage ratings are smaller**. Raw
Line Yards per Rush remains a separately named intermediate. The `model` table
publishes the common baseline, every context coefficient, penalties, decay,
feature revision, effective sample size, condition number, data rank, equation
residual, and whether identification depends on regularization. Disconnected
or sparse schedules can therefore produce a fit without pretending that the
data alone establishes a unique national ordering.

## Parameter selection, priors, and uncertainty

Without `parameters`, the recipe selects a candidate using the last two
available chronological validation weeks (one fold for two source weeks).
Each fold trains only on earlier weeks and games starting before the earliest
held-out game. Validation predictions use zero centered effects for unseen
levels and report unsupported-play counts. Selection minimizes pooled
unweighted validation MSE with a stable candidate-ordinal tie-break.

The default search space has team/context penalties `(16, 64)`, `(64, 256)`,
`(256, 1024)`, crossed with no decay or a 28-day half-life. These are search
candidates, not externally validated optimum penalties. Supply `candidates`
to define up to eight distinct configurations. The calibration table exposes
every candidate's folds, evaluated plays, unsupported plays, squared error,
MSE and selection. No usable holdout predictions selects no model; observed
raw metrics and coverage remain available, with null adjusted ratings.

For a frozen, previously selected configuration, pass
`ALYParameters(team_penalty=..., context_penalty=..., half_life_days=...)` via
`parameters`; the calibration policy is then `explicit`. A one-week run needs
frozen parameters. The recipe does not claim validated predictive superiority
over raw rushing measures without an independent historical evaluation.

When composing an outer workflow, pass an earlier `line_yards` workflow's
`["model"]` reference as `prior_model`. The model must precede the target season
and match the feature revision. The normal public callable uses no historical
prior unless one is composed explicitly. Priors must themselves be learned
without target-season leakage.

Uncertainty is conditional on penalties and prior means. With residuals `e_i`,
game scores `s_g = sum_i_in_g(w_i X_i e_i)`, and the coefficient block `B` of
the constrained system inverse:

```text
V_cluster = B [sum_g(s_g s_g')] B' * G / (G - 1)
standard_error_j = sqrt(V_cluster[j, j])
```

Fewer than two games returns null standard errors. These describe team effects;
they do not include hyperparameter-selection or baseline uncertainty. The model
also retains a separately labeled conditional residual-model variance.

## Evidence and reusable engine steps

Coverage is `present`, `partial`, `empty`, or `unavailable`. Ratings retain
evaluated rushes, unknown plays, excluded plays, unavailable games, and unknown
clock/score rushes. Missing game populations do not become zero yardage. Source
validation remains strict; unknown classifications are retained, while malformed
or contradictory evidence fails.

`cfb_data.analytics.modeling` exposes the reusable steps `categorical_design`,
`additive_statistics`, `fit_additive_model`, `predict_additive_model`,
`cluster_score_statistics`, and `additive_cluster_uncertainty`, with typed
configuration and output models. These steps contain no football rules. Other
recipes can reuse centered additive models, bounded normal equations, supported
predictions, and clustered uncertainty. `Table.from_pandas` admits already-owned
configuration/coefficient relations into native composition;
`Table.collect_bounded` is the explicit checked fitting boundary.

The [research report](../architecture/advanced-statistics-research.md) explains
the established metric families and feasibility of the remaining team-strength
and EPA recipes. Implementation tests independently calculate the constrained
fit and sandwich covariance, exercise unknown/excluded/absent data, and verify
fresh multipartition local/Dask execution plus pandas/Polars presentation.
Separately enabled Redis tests recompute both recipes with checkpoints disabled
and warm HTTP forbidden. Small-fixture parity is correctness evidence, not a
claim of season-scale speed or predictive accuracy.

The [verification report](../architecture/calculated-metrics-verification.md)
records the full quality contract, Redis acceptance, partition/task evidence,
and measured runtime, memory, encoding and shuffle workload.
