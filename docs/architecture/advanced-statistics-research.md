# Calculate four advanced college-football statistics

Research date: October 3, 2026. Repository evidence: commit
`99770ef01a1a0ae231269e0223c46f2d2e79b213`, package 0.9.0.
Status: Success Rate and opponent/situation-adjusted College ALY are implemented
as raw-play-derived recipes. See the [implementation guide](../guides/calculated-football-metrics.md)
for their exact contracts. The team-strength and EPA designs remain research.

The selected set is **Success Rate, opponent- and situation-adjusted College
ALY, an independently modeled SRS-derived team-strength rating, and own
Expected Points Added (EPA)**. The goal is complete calculated analytical
products, including the statistical complexity needed for accurate team
strength. Unadjusted Line Yards is an intermediate; plain SRS is a benchmark.
ALY requires a joint opponent/context fit. Team strength requires dynamic unit,
pace and special-team modeling. EPA and strength share substantial state/event
reconstruction work. No modeling requirement is deferred merely to simplify
the selected products.

Here, **net new means a new calculated analytical product**: every metric must
be derived from raw plays or game results. These are established statistics,
with project-owned specifications for ALY and the richer team-strength model.
The established metric families motivate these designs; no source has validated
our proposed model's accuracy. Similar values are available upstream; reading,
renaming, averaging, or joining those advanced values does not satisfy this
proposal. The added value is inspectable calculations, reproducible cutoffs,
custom splits, declared denominators, and evidence explaining every exclusion.

## Selection and feasibility

“Highly regarded” is supported here by documented adoption by established
college-football analysts or analytical projects, rather than an asserted
universal ranking of metrics.

| Calculated product | Evidence of established use | Raw inputs available here | Feasibility and main gap |
| --- | --- | --- | --- |
| Yardage Success Rate | Ed Feng's [The Power Rank methodology](https://thepowerrank.com/2021/10/21/5-insights-from-college-football-success-rate/) uses down-and-distance success to evaluate college offenses and defenses. | Historical plays: down, distance, yards gained, type, field position, offense and defense; games for IDs and season. | High after validating the play taxonomy, goal-to-go distance, and turnover handling. No fitted model. |
| Opponent- and situation-adjusted College ALY | [FTN's ALY methodology](https://ftnfantasy.com/dvoa/nfl/adjusted-line-yards) and [Connelly's college analysis](https://www.rockmnation.com/2012/10/19/3521402/bye-week-to-do-list-assess-james-franklin) establish the metric concept. | Historical rushing gains, down/distance/field position/time, joined to game participants. | Core fit is source-feasible; requires validated rushing attribution, score-state context, joint offense/defense fitting, normalization and uncertainty. Formation evidence is unavailable. |
| Dynamic SRS-derived team strength | [Sports Reference's SRS](https://www.sports-reference.com/blog/2015/03/srs-calculation-details/) supplies the opponent-adjustment baseline; [college unit-adjustment research](https://arxiv.org/html/2210.12519) and [Fremeau's possession definitions](https://bcftoys.com/notes) motivate the richer design. | Games, plays, drives, score events, elapsed time, field position and unit-specific events. | Substantial required source/modeling work: chronology, scoring/ST attribution, dynamic fitting, legal simulation and held-out accuracy evidence. |
| Independently modeled EPA per Play | [cfbfastR's college EP methodology](https://cfbfastr.sportsdataverse.org/articles/college-football-expected-points-model-fundamentals-part-i.html) and [EPA guide](https://cfbfastr.sportsdataverse.org/articles/college-football-expected-points-model-fundamentals-part-iv.html) provide an open college implementation. | Most preplay state fields, scores, possession names and IDs, plus drives and final game scores. | Conditional: chronology, score timing, event labels, training coverage and calibrated model artifacts are not established by current recipes. |

This is a **code/schema feasibility assessment**. No authenticated API calls,
season profiling, predictive backtest or performance benchmark were performed.
Available columns do not prove complete historical coverage or paid-tier access.
The implementation must first profile the explicitly chosen seasons and games.

SP+, FPI and FEI were considered. They are established systems, but their public
descriptions do not supply a complete reproducible specification for matching
the published values. [CFBD's SRS tutorial](https://radsportsanalytics.com/blog/talking-tech-bu/)
notes that SP+'s combination of factors is not fully disclosed;
[Brian Fremeau describes FEI](https://www.bcftoys.com/fei/) as opponent-adjusted
possession efficiency. The selected model uses a fully declared project
methodology rather than claiming to reproduce those published ratings.
Copying their API ratings would fail the requested
calculation requirement. CPOE and individual blocking grades also need richer
pass-location or charting evidence than the historical play schema provides.

## What our current sources actually provide

The following links point to the audited repository revision, not an old
implementation roadmap.

| Source or recipe | Relevant evidence | Constraint for calculated metrics |
| --- | --- | --- |
| [Historical `Play` model](https://github.com/ryanpaulanderson/cfb-data/blob/99770ef01a1a0ae231269e0223c46f2d2e79b213/cfb_data/cfb_data/plays/models/pydantic/responses.py#L49) | `game_id`, `id`, `drive_id`, nullable `drive_number`/`play_number`, offense/defense names and scores, period, nullable clock components, `yards_to_goal`, down, distance, gain, `scoring`, type/text and nullable `ppa`. | No historical success, rush/pass, garbage-time, turnover or penalty/no-play flags; no historical team IDs or ready-made next state. The schema permits down/distance zero and does not cap yards-to-goal at 100. Score timing is not specified. |
| [Historical `plays` recipe](https://github.com/ryanpaulanderson/cfb-data/blob/99770ef01a1a0ae231269e0223c46f2d2e79b213/cfb_data/cfb_data_recipes/plays.py) | Preserves raw state and PPA; adds nullable `clock_seconds`. Requires `year` and `week`. | `game_id` filters a containing play partition after retrieval. A season recipe must enumerate finite week/phase selectors; lexical play-ID sorting is not evidence of chronology. |
| [Drives](https://github.com/ryanpaulanderson/cfb-data/blob/99770ef01a1a0ae231269e0223c46f2d2e79b213/cfb_data/cfb_data_recipes/drives.py) | Game/drive identity, source result, start/end field position and offensive/defensive scores, period/clocks and score changes. | Useful reconciliation evidence. A drive's result label or score difference alone does not prove which play produced an offensive score. |
| [Team-game perspectives](https://github.com/ryanpaulanderson/cfb-data/blob/99770ef01a1a0ae231269e0223c46f2d2e79b213/cfb_data/cfb_data_recipes/team_games.py) | Two rows per game, keyed by `(game_id, team_id)`, with opponent ID, season, phase, completion, classification and score evidence. | The signed `point_differential` is known only for a proven result. Future and incomplete games remain in the source universe. |
| [Play-player stats](https://github.com/ryanpaulanderson/cfb-data/blob/99770ef01a1a0ae231269e0223c46f2d2e79b213/cfb_data/cfb_data_recipes/play_player_stats.py) | Athlete/team/play relationships and stat types; adaptive retrieval with explicit partial coverage. | Multiple athlete/stat rows per play can multiply denominators. The endpoint caps responses at 2,000 rows. Team metrics should not require this source; athlete extensions need deduplicated role associations and coverage. |

The current team-game/team-season enrichments already carry upstream success,
line yards, PPA, SRS and other ratings. Live play EPA/success are upstream values
as well. All of these must be excluded from calculation inputs. They may later
serve as separately labeled comparison data after reconciling their definitions.

## Shared analytical population

These are proposed defaults and consequential decisions to confirm before
implementation. They belong in recipes, not in the retrieval layer.

- Retrieve an unfiltered play-type population for each explicit week/phase;
  retain all rows for coverage and event evidence before choosing metric rows.
  Do not retrieve only “successful” plays or only rows with nonnull API PPA.
- Resolve offense and defense against the selected game's two participants
  using game ID and validated source names. Preserve source spelling and
  identity evidence; ambiguous or outside-game matches fail. A conference
  string is not a reliable substitute for season-specific classification.
- Success Rate and College ALY report regulation scrimmage plays for completed
  games; EPA uses the separately declared regulation next-score horizon. Keep
  overtime, kicks, returns, tries, kneels, spikes and administrative/no-play
  rows as explicit exclusions. Genuine sacks count as dropbacks in the
  passing split and are excluded from the rushing population. This is an
  analytical convention, distinct from NCAA rushing box-score accounting.
  The team-strength model needs the full scoring/clock/special-team event
  universe and legal overtime rules; these events must not inherit a
  scrimmage-summary exclusion.
- Own a versioned play-type vocabulary. Classify rushes, completions,
  incompletions, interceptions, sacks, fumbles and scoring/administrative
  events using tested structured evidence. Broad substring matching on text
  must not silently establish validity. Unresolved eligible-looking rows
  retain an unknown result and a reason.
- Validate eligible state domains: down 1–4, positive distance, consistent
  goal-to-go distance, and ordinary preplay field position inside the field.
  Do not silently repair contradictions with `min(distance, yards_to_goal)`.
  Source-valid administrative rows can have zero down/distance and remain
  valid exclusions; contradictory scrimmage evidence fails.
- Initially include all regulation score situations. Any garbage-time filter
  must define its own score/period thresholds, prove preplay score timing,
  and change the semantic identity. Historical retrieval supplies no such flag.
- Preserve the completed team-game universe when attaching summaries. A
  requested game with absent plays has unavailable metrics, not zero success.
  Valid partial input may yield a labeled partial result; invalid or
  contradictory input must fail.

Each output needs `source_rows`, `eligible_rows`, `evaluated_rows`,
`unknown_rows`, counts by exclusion reason, and retrieval/reconciliation status.
Here, `eligible_rows = evaluated_rows + unknown_rows`. A known empty population
has a null rate with zero denominator; missing coverage also has a null rate,
with its different reason preserved. A partial rate uses evaluated rows and
must visibly retain the unknown count. Do not advertise source completeness
merely because all requested HTTP calls succeeded.

## 1. Yardage Success Rate

### Meaning and math

This measures how consistently an offense gains enough yards for the current
down. Use the established **50% / 70% / 100%** college definition described by
[Ed Feng](https://thepowerrank.com/2021/10/21/5-insights-from-college-football-success-rate/).
Other historical definitions differ, so publish the thresholds with the metric.

For eligible play `i`, let `d_i` be preplay yards needed for a first down or
touchdown and `y_i` the credited offensive gain. Let `T_i` indicate a verified
turnover lost by the offense. The proposed turnover-aware version is:

```{math}
a_i = \begin{cases}
0.50 & \mathrm{down}_i=1\\
0.70 & \mathrm{down}_i=2\\
1.00 & \mathrm{down}_i\in\{3,4\}
\end{cases},\qquad
s_i = \mathbf{1}[y_i\ge a_i d_i]\,\mathbf{1}[T_i=0].
```

```{math}
\mathrm{SR} = \frac{\sum_{i=1}^{N}s_i}{N}.
```

The turnover override follows a variant visible in
[cfbfastR's implementation](https://github.com/sportsdataverse/cfbfastR/blob/main/R/create_epa.R);
it is an explicit choice beyond the yardage threshold. Missing turnover
evidence makes the flag unknown rather than assuming possession was retained.
Keep this metric distinct from `EPA > 0`, which is another meaning of success.

Store rates as fractions in `[0, 1]`; presentation may multiply by 100.
Offensive SR is better when higher. `success_rate_allowed` keeps the offensive
definition for plays faced by the defense, so lower is better.

Invented example: a gain of 5 on first-and-10 succeeds, 4 on second-and-6 fails,
and 3 on third-and-3 succeeds, assuming no turnovers. SR is `2 / 3 = 66.67%`.
Second-and-6 requires 4.2 yards; with integer gains, 5 is the first successful
gain. Never round the threshold down. A lost fumble after gaining the threshold
fails under the proposed turnover-aware rule. A recovered offensive fumble is
not automatically a failure. Penalty-awarded first downs are outside this
yardage-based population rather than inferred from the next down.

### Recipe design and feasibility

```text
plays(year, week, phase) + team_games(year, phase)
  → resolve_game_participants
  → classify_scrimmage_plays + validate_success_inputs
  → derive_yardage_success
  → aggregate_success_counts_by_team_game_and_split
  → sum_counts_for_team_season
  → attach_to_declared_game_universe + validate_rates_and_coverage
```

All generic stages use native `Table` expressions/joins/aggregations. The
core expression on a table already containing validated, evaluable plays can
be written with the **existing** authoring surface:

```python
import narwhals.stable.v2 as nw

# eligible is a Table with validated state and turnover evidence.
flagged = eligible.with_columns(
    nw.when(nw.col("down") == 1)
    .then(nw.lit(0.5))
    .when(nw.col("down") == 2)
    .then(nw.lit(0.7))
    .otherwise(nw.lit(1.0))
    .alias("success_fraction")
).with_columns(
    (
        (nw.col("yards_gained") >= nw.col("success_fraction") * nw.col("distance"))
        & ~nw.col("turnover_lost")
    )
    .cast(nw.Int64)
    .alias("successful")
)
counts = flagged.aggregate(
    keys=("season", "game_id", "team_id", "play_family"),
    expressions=(
        nw.col("successful").sum().alias("successful_plays"),
        nw.len().alias("evaluated_plays"),
    ),
)
```

This is a transformation fragment, not an installed metric recipe. The
proposed classification fields, row models and universe/coverage joins still
need implementation. Season rates divide summed successes by summed plays;
averaging game percentages would incorrectly give small games equal weight.

Named outputs: `play_success`, `team_game_success`, `team_season_success`,
and `coverage`. The first is keyed by `(game_id, play_id)`; aggregate keys add
team ID and split. Retain numerator and denominator. Useful splits include
down, rush/dropback, standard/passing downs and field-position bands, provided
each split is defined and versioned.

**Assessment:** raw-field feasible with no new statistical dependency. The
primary work is trustworthy eligibility and turnover evidence. Acceptance
must include threshold boundaries, goal-to-go, sacks, penalties, recovered
versus lost fumbles, interceptions, excluded tries, unknown types, empty games,
and game/season groups split across partitions.

## 2. Opponent- and situation-adjusted college Line Yards

### Selected product and raw yardage math

The selected product is **College Adjusted Line Yards (College ALY)**.
Opponent adjustment, situation adjustment and league normalization are required
parts of its recipe. Raw Line Yards is an intermediate observation.

[FTN's ALY definition](https://ftnfantasy.com/dvoa/nfl/adjusted-line-yards)
describes yardage weighting, context/opponent/formation adjustment, and
normalization to league running-back yards per carry. It also cautions that
ALY cannot fully separate blocking from runner performance. College use is
evidenced by [Bill Connelly's analysis](https://www.rockmnation.com/2012/10/19/3521402/bye-week-to-do-list-assess-james-franklin).
The public descriptions do not give complete fitted coefficients; the model
below is our reproducible college specification, not an exact reconstruction
of a provider's published values.

For validated rushing gain `y`, first calculate:

```{math}
L(y)=\begin{cases}
1.2y & y<0\\
y & 0\le y\le4\\
4+0.5(y-4) & 4<y\le10\\
7 & y>10.
\end{cases}
```

Weights apply to segments. A 12-yard run receives seven line yards, and a
2-yard loss receives `-2.4`. Invented gains `[-2, 3, 6, 12]` yield line yards
`[-2.4, 3, 5, 7]`: raw `3.15 LY/rush` versus `4.75` ordinary yards/rush.
This establishes the response to adjust; it is not the finished ALY result.

The college population includes identified QB runs and scrambles as well as
other carriers. Exclude sacks, kneels, tries, kicks/returns, no-play rows and
identified fumble events; fumble recovery/return yardage cannot become rushing
credit. Unknown rush/fumble/penalty attribution remains unknown. This differs
explicitly from FTN's running-back-only scope. Team-level college ALY does
not require a player association. An RB-only population would require verified
ball-carrier roles, season-specific roster positions and the capped
`play_player_stats` source; absent associations must not become exclusions.

### Fit offense and defense together

For rush `i`, let `o_i` and `d_i` be offense and defense IDs, `z_i=L(y_i)`,
and `c_i` its measured game context. Use the joint model:

```{math}
z_i=\mu+a_{o_i}-b_{d_i}+f_\beta(c_i)+\epsilon_i.
```

Positive `a` means better offensive line-yard production. Positive `b` means
stronger defensive prevention; it reduces allowed yardage. Estimate both
simultaneously across the selected schedule. Correcting each offense using an
opponent's unadjusted rushing average would leave that opponent's schedule
and situations inside the adjustment.

Use explicit, versioned context features:

| Feature | Proposed observed-data contract |
| --- | --- |
| Down | 1, 2, 3, 4 |
| Distance | 1–2, 3–5, 6–10, 11–15, 16+ yards |
| Preplay yards-to-goal | 1–5, 6–10, 11–20, 21–50, 51–80, 81–99 |
| Core interaction | Joint down × distance × field-position cells, totaling 120 |
| Time | Quarter; final 120 seconds of halves; an explicit unknown-clock category |
| Venue | Home, away or neutral for the offense, established from the game |
| Score situation | Verified preplay score margin and its interaction with time, after proving historical score timing |
| Era | Season/rule-era effects where a stable multi-season baseline is used |

Include score/time context in the selected model once the shared event-state
adapter proves it. Do not copy a future-dependent garbage-time flag. Formation,
box count, run direction, blocking personnel and contact yards are absent
from the current historical schema. Record that unsupported context; never
infer shotgun formation from residuals or claim a formation-adjusted result.

Fit constrained, regularized weighted least squares, with explicit team prior
means `p_a`/`p_b` learned from our own earlier-season results:

```{math}
\min_{\mu,a,b,\beta}
\sum_i w_i\left[z_i-\mu-a_{o_i}+b_{d_i}-f_\beta(c_i)\right]^2
+\lambda_a\|a-p_a\|_2^2+\lambda_b\|b-p_b\|_2^2
+\lambda_c\|\beta\|_2^2,\qquad
w_i=2^{-\mathrm{age}_i/\tau}.
```

`tau` is a positive half-life in days. Penalty scales, half-life, offseason
regression and context complexity are learned through earlier rolling
validation windows; the report does not assert untested production defaults.
Require finite positive penalty scales and half-life; an equal-weight candidate
uses an explicit no-decay policy. Store the selected values, feature basis and
centering constraints with the model artifact.
For an unavailable earlier-season prior, use an explicit average prior with
increased uncertainty and an availability reason. No API ALY/rating may enter
the fit or prior.
Recenter historical prior means under the current weighted reference
population; prior-season exposure centering does not automatically carry over.

Let `n_o` and `n_d` be sums of fitted rush weights for each offense/defense.
Require exposure-weighted centering:

```{math}
\sum_o n_o a_o=0,\qquad \sum_d n_d b_d=0,\qquad
\sum_i w_i f_\beta(c_i)=0.
```

Center the separately coded context blocks as well to remove redundant
intercept directions. Leave `mu` unpenalized. These constraints make `mu`
the weighted league mean of raw line yards. Ridge stabilizes sparse effects;
it does not create missing matchup evidence. Check the offense-versus-defense
bipartite design rank and component membership, rather than only connectivity
of the ordinary team schedule. Publish prior dependence and interval width.

### Standardize and normalize the adjusted results

Evaluate every offense against an average defense and every defense against
an average offense, using the **same fitted league situation distribution**.
Under the centering above, standardized offensive LY is `mu + a_o` and
standardized defensive LY allowed is `mu - b_d`.

Let the weighted ordinary rushing average of the exact eligible population be:

```{math}
\bar y=\frac{\sum_i w_i y_i}{\sum_i w_i}.
```

Apply the explicit additive normalization `k = bar_y - mu`:

```{math}
\mathrm{College\ ALY}_o=\bar y+a_o,\qquad
\mathrm{College\ ALY\ allowed}_d=\bar y-b_d.
```

The exposure-weighted league mean of each is exactly ordinary eligible-population
yards/rush. This is our specified normalization, not a claim that FTN uses
this algorithm. It preserves adjusted differences and remains defined when
the line-yard baseline is zero or negative. Higher offensive ALY and lower
defensive ALY allowed are better. Adjusted values are not limited to the
seven-yard raw-credit ceiling.

Invented fitted example: league ordinary YPC is `4.75`, fitted offense effect
is `+0.40`, and an opponent's defensive prevention effect is `+0.60`.
The offense's standardized ALY is `5.15`. At otherwise identical context,
the fitted observation against that defense loses `0.60` line yards; the
adjustment accounts for that difficulty. A defense with effect `+0.60` has
standardized ALY allowed `4.15`. These are illustrations, not fitted results.

An optional index is `100 * ALY / bar_y` when `bar_y > 0`, with average 100.
Keep yards/rush as the primary result and keep negative estimates visible.
For held-out game diagnostics, remove fitted opponent/context effects from
observations and add the normalization shift. Label that observed game
score separately from the shrunken season rating; their averages are not
interchangeable.

```{math}
z_i^{\mathrm{adjusted,off}}
=z_i+b_{d_i}-f_\beta(c_i)+(\bar y-\mu).
```

Here all fitted quantities precede the held-out game. The plus sign on the
defensive effect restores yardage suppressed by a strong opposing defense.

### Recipe, feasibility and acceptance

```text
explicit raw-play partitions + authoritative game participants
  → validated rush population, gains and measured preplay context
  → native line-credit, context-feature and weight expressions
  → native model sufficient statistics and exposure reductions
  → bounded constrained fit + coefficients/context/diagnostic tables
  → common-opponent/common-situation standardization
  → league normalization + coverage + uncertainty
```

Native reductions produce coefficient-scale `X^T W X`, `X^T W z` and weighted
moments; do not gather a season of Python play models. The coefficient solve
is an explicit new modeling boundary. NumPy already supports the bounded
linear algebra; a larger sparse context/dynamic specification may justify
a sparse numerical dependency through the packaging policy. Game-cluster
resampling or a validated model uncertainty procedure must accompany rankings.

Named products: `rush_features`, `team_game_adjusted_line_yards`,
`team_adjusted_line_yards`, `model_parameters`, `model_diagnostics`, and
`coverage`. Preserve raw credits/counts, adjusted effects, reference mixture,
normalization baseline, weighted exposure, cutoff, prior, coefficient/model
digest and unsupported-context metadata.

**Assessment:** pursue the full opponent/situation-adjusted metric. The
raw fields support its core fit; source profiling, score-state reconstruction,
modeling contracts and calibration are required work. ALY remains a team
run-blocking proxy, rather than an individual or causal line grade.

Acceptance must recover independently specified offense/defense effects from
unequal synthetic schedules, adjust identical raw gains differently for strong
and weak defenses, and standardize unequal context mixes. Prove weighted
normalization, correct defense sign, prior/rank-deficient behavior, no
athlete-join duplication, zero/unavailable distinctions and cross-partition
sufficient-statistic parity. Validate on later games against raw LY and
context-only adjustment, reporting held-out error, context calibration,
uncertainty, prior sensitivity and coverage. Reject invalid evidence; retain
valid partial results with their uncertainty and missingness visible.


## 3. Estimate team strength with a better SRS-derived model

### Product goal and selected design

The product is **one independently calculated team-strength rating** whose
meaning is expected neutral-field point margin against a standardized average
opponent. Greater predictive accuracy is the goal, and substantial statistical
and architectural work is in scope. The original SRS structure does not limit
the selected design. Score-only SRS is an evaluation benchmark.

Use a **dynamic hierarchical possession model**. It learns offensive,
defensive, special-teams and pace behavior against the opponents actually
faced, then predicts whole games using their changing states and legal
scoring/possession rules. Home field, starting field position, score/time
strategy, turnovers and uncertainty are integral model components.

Methodological grounding includes [Glickman and Stern's state-space score
model](https://www.glicko.net/research/nfl.pdf), which supplies an NFL precedent
for changing strength and predictive uncertainty; [college research on
opponent, venue and complementary-unit adjustment](https://arxiv.org/html/2210.12519);
and [Brian Fremeau's possession and unit definitions](https://bcftoys.com/notes).
These support the approach. They do not provide this project's complete model
or establish its college prediction accuracy.

### A joint model of possession outcomes

At possession `d`, let the state contain offense/defense, date, starting
yards-to-goal, game phase and half, half-seconds, pre-possession margin, venue
and rule era. The overtime adapter adds overtime period and possession index;
an unclocked phase has no invented half-clock value. Opening and halftime
receiving assignments remain persistent game-protocol metadata. Together these
fields distinguish a halftime restart from regulation or overtime termination.
The primitive outcome is `z_d = (K_d, B_d, L_d, A_d)`:

- `K`: scrimmage termination, from TD, field-goal attempt, punt, interception,
  lost fumble, turnover on downs, safety, or end of half;
- `B`: ending field position, constrained by that outcome;
- `L`: clock consumed, including legal zero-time and half-end outcomes;
- `A`: the associated return, kick, conversion and restart event chain.

For termination class `k`, use a multinomial outcome model:

```{math}
\Pr(K_d=k\mid x_d,\theta,u_g)
=\frac{\exp(\eta_{dk})}{\sum_j\exp(\eta_{dj})},\qquad
\eta_{dk}=\beta_k^{\mathsf T}\phi(x_d)
+a_{o_d,k}(t)+b_{d_d,k}(t)+u_{g,k}.
```

`a` and `b` are time-varying offensive and defensive effects; their signs
depend on the outcome class. A larger defensive interception coefficient is
not equivalent to a larger defensive TD-allowed coefficient. Obtain readable
unit strength from counterfactual expected points, not raw coefficient signs.
Choose a reference class with zero logit and separately center offense and
defense effects for every other class. Use proper hierarchical priors.

Publish the bounded spline/interaction basis `phi`: field position, time,
pre-possession score margin, home/away/neutral venue and rule era. Necessary
interactions include field position by outcome and score margin by time.
Context is observed at the event start during fitting and generated during
future prediction. Do not invent unobserved injuries, formation or weather.

The likelihood factors **conditionally**, rather than pretending separate
aspects of the same possession are independent copies of its scoring outcome:

```{math}
p(z_d\mid x_d,\theta,u_g)
=p(K_d\mid x_d,\theta,u_g)
\,p(B_d\mid K_d,x_d,\theta)
\,p(L_d\mid B_d,K_d,x_d,\theta)
\,p(A_d\mid B_d,L_d,K_d,x_d,\theta).
```

Specify `B` with probabilities on legal yardlines, smooth field effects and
regularized offense/defense terms. Specify duration with a conditional
distribution on the available half-clock interval, explicit zero-duration
and terminal atoms, and offense/defense pace effects. Ordinary events cannot
consume more than the available clock. Quarter/half boundaries and changes
in clock rules belong to the versioned era adapter.

The event-chain model includes field-goal make/miss/block by kick distance,
punt field position and returns, interception/fumble returns, conversions,
kickoffs/onside recoveries and possession exceptions. Fit special-team role
effects for kicking, returning and coverage; partially pool rare events.
Special teams changes the generated field positions and scores inside the
same model, so no separate arbitrary special-teams bonus is needed.

Use shared game noise `u_g ~ Normal(0, Sigma_game)` to represent within-game
dependence. A future game draws new noise; its unseen observations cannot
estimate that draw. Preserve dependence in resampling, fitting and uncertainty.

### Actual scoring and transitions

Own a disjoint scoring-event ledger: a touchdown contributes six, followed by
the actual/generated legal conversion; return TDs, field goals, safeties and
rare legal defensive conversion scores belong to their scoring team exactly
once. Starting kickoffs and halftime restarts are explicit events too.
Reconcile the observed ledger with final scores before fitting.

```{math}
r_d=\sum_{a\in d}
\left[\mathrm{pointsFor}(a)-\mathrm{pointsAgainst}(a)\right],\qquad
x_{d+1}=F_e(x_d,z_d).
```

`F_e` is the tested legal transition for that rule era. It updates field
position, score, clock and possession, including same-team recoveries,
halftime and regulation termination. Support overtime through its own legal
state/rule adapter; do not add a made-up winning-margin floor. Historical
tie rules also need an explicit era policy.

The actual-score ledger differs deliberately from EPA's next-score convention
of TD=7. That EPA convention cannot become this model's scoring rule. A
returned interception score must not also become offensive drive scoring.

### Dynamic strength, priors and independent play signals

Let `theta_i(t)` contain the team's offensive, defensive, pace and special-team
states. A season-transition prior and within-season evolution can be specified as:

```{math}
\theta_{i,s,0}\sim
\mathcal N\!\left(\rho_{\mathrm{off}}\theta_{i,s-1,\mathrm{end}}
+Bz_{i,s},\Sigma_{\mathrm{off}}\right),\qquad
\theta_i(t+\Delta)\mid\theta_i(t)
\sim\mathcal N\!\left(\rho^{\Delta}\theta_i(t),Q_{\Delta}\right).
```

The previous season's own posterior supplies a prior with offseason regression
and increased uncertainty. Verified preseason roster/recruiting/coaching
features may enter `z`; absent historical personnel evidence is not replaced
by today's roster or an API power rating. Hyperparameters and transition
variance are learned from earlier training/validation seasons, not chosen to
make a current ranking look plausible.

Independently calculated rush/pass Success Rate, opponent-adjusted ALY,
explosive-play and turnover tendencies can inform predictive covariates
available **strictly before** each game. Own EPA can do so after its model
contracts pass. Estimate contributions and nonlinear interactions in the
training boundary, with partial pooling and ablation checks. These overlapping
summaries do not become independent additional scoring observations.

Avoid fitting final scores, margins, wins, drive points, SR and EPA as separate
likelihood factors for the same complete game. The primitive event process
supplies its evidence once; scores and derived metrics provide reconciliation
and posterior-predictive checks. Historical feature/model packs are rebuilt
chronologically or cross-fitted, with their uncertainty retained.

Fit the full selected opponent network before filtering requested teams.
Represent FCS opponents by their own identities and appropriate hierarchical
classification priors when their source evidence is available; never merge
all lower-division teams into one invented opponent. Weakly observed opponents
retain uncertainty. For complete-event games use the primitive likelihood.
For games with only valid final-score evidence, a supported marginalized
score likelihood from the same process may retain that information; do not
multiply it by a complete-event likelihood for the same game. Integrating
missing event paths is explicit modeling work, not a silent zero or imputation.

Disconnected schedules can share a prior scale, but comparative evidence
remains weak. Publish component membership, prior sensitivity and intervals.
Historical pregame states use the filtered posterior given data available
at that cutoff. Full-season retrospective smoothing is a separately labeled
analysis and cannot enter predictive backtests.

### One strength rating and direct matchup predictions

Using the posterior at cutoff `T`, simulate games with a neutral venue and a
shared opening/halftime protocol fitted or specified from training data.
Make that protocol exchangeable under team-label swaps: balance the initial
receiving assignment and use its complementary halftime restart. Noise and
rule conventions must preserve the same symmetry, yielding zero self-matchup
expectation and opposite expected margins when team labels swap.
Use generated field position, drive outcomes, pace, score progression and
rule-era overtime. Do not condition on the future game's realized possessions
or starting fields: those are outcomes, and conditioning on them can also
erase deserved defensive and special-team contributions.

For posterior draw `m`, define expected matchup margin and team rating:

```{math}
M_{ij}^{(m)}
=\mathbb E[\mathrm{score}_i-\mathrm{score}_j
\mid\theta^{(m)},\mathrm{neutral\ protocol}],\qquad
R_i^{(m)}=\frac1K\sum_{j\in\mathcal R}M_{ij}^{(m)}.
```

The declared reference population `R` uses uniform team weights; self-matchup
expectation is zero. Center reported strengths over that population and
publish expected points above average, posterior intervals and rank
probabilities. Use the same reference protocol for all teams; it does not
fix future possession counts, which the model generates.

Actual matchup predictions come directly from the simulator. In this nonlinear
model, a difference of two headline ratings is generally not the expected
head-to-head margin. Output matchup margin distribution, win probability,
score distribution and predictive intervals. Simulation error is separate
from posterior uncertainty and must be bounded and reported.

Explain offense, defense and special teams by replacing one unit with the
reference unit distribution in the same model. These comparisons describe
contributions and interactions; they need not add exactly to the overall rating
and are not causal player grades.

### Relationship to SRS and acceptance benchmark

The model retains SRS's simultaneous opponent adjustment. Under a simple
linear per-possession value with fixed common possession count `N`:

```{math}
\mathbb E[Y_{i\to j}]=\mu+O_i-D_j,\qquad
\mathbb E[M_{ij}]
=N\left[(O_i+D_i)-(O_j+D_j)\right].
```

That is the familiar difference-of-strengths structure. The selected model
learns much more than a single season scoring margin: unit interactions,
changing ability, field-position transitions, pace and actual scoring rules.

For an independent simple benchmark, compute score-only SRS from completed
raw games, with no advanced-rating endpoint. For rating `r_i`, mean adjusted
margin `mbar_i` and opponent `o(i,g)`:

```{math}
r_i=\bar m_i+\frac1{n_i}\sum_{g\ni}r_{o(i,g)},\qquad
\sum_i r_i=0.
```

[Sports Reference's documented college variant](https://www.sports-reference.com/blog/2015/03/srs-calculation-details/)
floors winning-margin magnitudes at seven and caps them at 24. Also compare
raw-margin SRS. An invented check is A beating B by 14 and C by 7, with C
beating B by 7: centered SRS is A `+7`, C `0`, B `-7`. Benchmark input scope
and classification must be stated. SRS already adjusts opponents; another
unmodeled SOS bonus would duplicate that adjustment.

### Recipe, feasibility and required evidence

```text
explicit plays + drives + games + training/cutoff specification
  → game identities and globally verified event chronology
  → primitive possession/state/scoring/return/kicking/clock tables
  → own historical play features and opponent-adjusted ALY
  → partitioned model inputs + dynamic joint fit + posterior artifacts
  → bounded legal game simulations against reference/matchup opponents
  → team_strength / unit_explanations / matchup_predictions / diagnostics
```

Existing raw sources provide much of the state evidence, but reliable score
timing, chronology, special-team attribution, conversions, elapsed clocks and
legal transitions must be proved by season profiling and fixtures. A current
completion flag and start time do not establish historical availability;
use captured cutoff snapshots, or label retrospective season/week evidence
accordingly. Missing observations stay missing, rather than becoming neutral
or average events.

The current native engine can build validated partitions, relational features
and immutable table artifacts. It lacks the selected dynamic fitting,
posterior and simulation subsystem. Add typed fit/inference interfaces,
canonical parameter/posterior artifacts, deterministic seeds, convergence
diagnostics, resource bounds and recovery contracts. Evaluate sparse numerical
and probabilistic inference dependencies on maintained support, numerical
reliability and operational value. No new dependency is installed by this
research report.

Domain sequence/transition kernels require co-located bounded game/half input
and explicit schemas. Generic joins/reductions remain native. Statistical fit
and simulation are visible model boundaries; neither is an all-season list
hidden in `map_partitions`. Control posterior/sample/game-event bounds and fail
or report unmet precision rather than silently truncate simulated games.

**Assessment:** pursue the full team-strength model. It requires substantial
source and modeling architecture work, which is part of the selected scope.
Complexity is justified by independently measured accuracy and uncertainty,
not by claiming that more inputs guarantee better rankings.

Use rolling cutoffs across multiple untouched later seasons. Compare the
selected model with independently calculated clipped/raw SRS and static
possession models on margin MAE/RMSE, proper predictive log scores, win
Brier/log loss and interval calibration. Report early-season, venue, pace,
opponent-strength and coverage slices. Test score/possession/turnover/return/
clock distributions, parameter recovery, posterior approximation, prior
sensitivity and simulation precision. Ablate ALY, other play signals,
dynamics and special teams to establish their contribution. Greater accuracy
is an empirical acceptance criterion; this report has not performed a fit
or demonstrated superiority.


## 4. Independently modeled Expected Points Added

### Meaning and math

EPA measures the change in the scoring value of a situation across a play.
Use a **next-score-within-the-half** model, as in the
[college EP methodology](https://cfbfastr.sportsdataverse.org/articles/college-football-expected-points-model-fundamentals-part-i.html).
The state `x` contains preplay down, distance, yards-to-goal and seconds left
in the half. The proposed baseline excludes team names and score margin from
features; adding them changes meaning and needs a revision.

Predict probabilities of the next event in that half, signed from the current
offense's perspective:

| Event | TD | FG | Safety | No score | Opponent safety | Opponent FG | Opponent TD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Point value `v_k` | 7 | 3 | 2 | 0 | -2 | -3 | -7 |

```{math}
\mathrm{EP}(x)=\sum_{k=1}^{7}p_k(x)v_k,\qquad
\sum_kp_k(x)=1.
```

TD=7 incorporates an assumed extra point. PAT/two-point rows are not added
again. This convention is a model target, not a claim that every real
touchdown scores seven. An actual-conversion target would need another
specification.

For non-scoring transitions let `x_next` be the verified immediate next state
and `sigma` be `+1` for retained offense or `-1` for changed possession. Define
the horizon-consistent postplay value:

```{math}
V_i^+=\begin{cases}
v(\mathrm{event}_i) & \text{a scoring event ends the next-score horizon}\\
0 & \text{the half/game ends without a score}\\
\sigma_i\mathrm{EP}(x_{\mathrm{next}}) & \text{otherwise}
\end{cases},\qquad
\mathrm{EPA}_i=V_i^+-\mathrm{EP}(x_i).
```

```{math}
\mathrm{EPA/play}=\frac{\sum_i\mathrm{EPA}_i}{N}.
```

The terminal-score and possession-sign conventions are supported by
[cfbfastR's calculation code](https://github.com/sportsdataverse/cfbfastR/blob/main/R/create_epa.R).
Do not add both touchdown points and EP after the subsequent kickoff: that
would combine different horizons. A turnover returned for a touchdown uses
the opponent-score terminal value, not both that score and continuation EP.

Invented examples with preplay EP `1.2`: continuation at EP `2.0` produces
`+0.8 EPA`; opponent possession at its EP `1.6` produces `-2.8`; an offensive
TD produces `7 - 1.2 = +5.8`; a nonscoring half-ending play produces `-1.2`.
Units are points/play. Defense `epa_allowed` retains the offensive sign and
is better when lower. A separately named defensive contribution may negate
it. Raw EPA does not itself adjust for opponent quality or divide credit
among the passer, receiver, blockers and coach.

### Own an explicit expected-points model

An independently estimated model can begin with a transparent, smoothed
state-cell estimator. This is a **proposed project model**, not a reproduction
of CFBD PPA, ESPN EPA or cfbfastR's fitted model.

Map state to a cell `b` using down, distance bands, 5-yard field-position
bands and half-time bands. Publish exact bin edges, boundary behavior and a
finite cell bound before fitting. Let `n_bk` count training states in cell `b`
whose next event has class `k`, `n_b = sum_k n_bk`, and `q_k` be training-only
global event frequencies. With explicit smoothing weight `alpha > 0`:

```{math}
\hat p_{bk}=\frac{n_{bk}+\alpha q_k}{n_b+\alpha},\qquad
\widehat{\mathrm{EP}}(b)=\sum_k\hat p_{bk}v_k.
```

Fit counts with native group reductions. The model is a bounded table of
cell keys, counts, probabilities and EP, making inference a checked
many-to-one join. Training-unseen cells use the declared smoothed prior but
must be labeled out-of-support; do not silently treat such estimates as
equally well supported. Reject inference states outside the model's physical
domain. Choose bins and `alpha` on chronological validation data, then freeze
them for final evaluation. Failure to achieve acceptable calibration means
the metric remains research rather than a ready analytical product.

More flexible regression/boosting is possible later, with a justified
dependency and fitting boundary. It is not required to explain or implement
the baseline math. Model fitting, labels and immutable model representation
are new responsibilities; current recipes do not supply a training facility.

### State reconstruction and recipe design

```text
explicit training seasons/weeks + target seasons/weeks
  → plays + drives + games
  → validate_game_participants_and_complete_sequence_evidence
  → normalize_preplay_states_and_scoring_events
  → derive_half_boundaries_and_next_score_training_labels
  → native training cell counts + smoothed_model_cells

target normalized states + frozen_model_cells
  → global successor-state join + terminal values
  → native pre/post EP lookup and EPA arithmetic
  → team/game/season aggregation + coverage and model diagnostics
```

Before implementation, prove these source contracts using representative
scoring, turnover, penalty and period-boundary fixtures:

1. **Chronology:** nullable drive/play numbers and clocks do not prove a
   complete ordered chain. Validate a unique chronological key. The existing
   `Table.sort(...).with_group_index(..., keys=("game_id",))` can assign global
   ordinals after that proof. Join shifted ordinals globally for adjacency;
   partition-local `shift` loses transitions at boundaries.
2. **Score timing and events:** establish whether each historical score field
   is preplay or postplay, resolve scoring team/type, and reconcile with drive
   endpoints and final game totals. `scoring=true` alone is insufficient.
3. **Horizon:** labels may look through multiple drives to the next scoring
   event in the same half. A punt is not a zero-point terminal label. Nonscoring
   halftime is terminal; the end of quarters 1 and 3 is not. Regulation-only
   inference excludes overtime and explicitly reports it.
4. **Administrative rows:** preserve kicks/returns/scoring evidence while
   constructing labels, then apply the final metric population. Enforcement
   and no-play events must be linked correctly to avoid double counting.
5. **Missing evidence:** a missing successor, clock or event is unknown,
   never silently a half-end or zero EP. Reconstruction should not jump over
   an unresolved event to create a plausible transition.

The next-score labeling/normalization adapter is explicit new architecture
work. If sequential domain decoding is necessary, shuffle/co-locate by game
or half first and enforce a per-game row/resource bound before a kernel runs.
Declare its input/output schema, ordering, null handling and cardinality.
Do not place an all-season list or an unbounded all-pairs future-event join
inside a worker. Generic joins, filtering and aggregation stay native.

Named products: `play_epa`, `team_game_epa`, `team_season_epa`, `model_cells`,
`model_diagnostics`, and `coverage`. Include model ID/digest, training window,
feature/bin contract, point-value convention, evaluated count, support flags
and excluded/unknown counts. Sum EPA and counts to obtain seasonal rates;
do not average game EPA/play values without their denominators.

**Assessment:** plausible with the present raw sources, but not ready merely
because a nullable `ppa` column exists. Train on earlier seasons and evaluate
on held-out later seasons, keeping whole games together. Future scoring events
are legitimate training labels; they must never enter preplay features.
Inspect multiclass log loss/Brier score, class calibration, rare-event counts,
support coverage, uncertainty and plausible down/field-position curves.
Use game-level resampling for uncertainty rather than treating plays sharing
the same scoring event as independent. Report comparison with simple baselines
before claiming predictive value. A model trained on future seasons must not
be used for historical pregame backtests.

## Fit these designs to the current recipe engine

Follow [ADR 0007](0007-native-table-execution.md) and the
[current authoring guide](../guides/modular-analytics.md). The
[original execution audit](recipe-dask-reengineering-audit.md) is baseline
context; it does not mean that the current native migration is pending.

The named stages above are proposals, not existing imports. Implement them
as independently importable modules with `@step` transforms taking and
returning `Table`, typed Pydantic output models, and `@dataset` declarations
for grain, keys, ordering and semantic partitions. A `@workflow` can expose
the related named products. Keep metrics out of endpoint response models.

| Responsibility | Existing support and required design |
| --- | --- |
| Planning | `.plan()` is pure. Validate finite explicit season/week/phase selectors and request limits before I/O. Source enumeration is bounded builder control flow; retrieved tables must not trigger arbitrary dynamic fan-out. |
| Computation | `Table.select`, `with_columns`, `filter`, `join`, `aggregate`, `sort` and `concat_tables` build native graphs. Use `require_unique` and explicit join cardinalities globally. A `map_partitions` domain kernel requires typed empty metadata and bounded input. |
| Missing populations | Left-join aggregates onto the declared completed team-game universe; never let an optional athlete/model source silently expand or shrink that universe. Keep coverage distinct from evaluated-play counts. |
| Source ownership | The coordinator owns HTTP, credentials, cache policy, retry/attempt accounting, validation and authoritative publication. No network calls or client/session objects belong in worker graphs. |
| Model/solver work | ALY needs a bounded joint coefficient fit; team strength needs dynamic inference/posterior/simulation contracts; EPA needs state-label/model contracts. These are selected product requirements and explicit modeling boundaries, not hidden gathers inside ordinary transforms. |
| Results | Direct calls retain the explicit eager pandas/Polars boundary. Durable runs may choose `ExecutionPolicy(result_mode="lazy")`; artifacts support `scan()` and bounded `batches()`. Named workflows expose each product explicitly. |
| Reuse | Recipe revision, semantic parameters and upstream artifact digests determine checkpoint compatibility. Thresholds, taxonomy, cutoffs, classification, margin policy, model cells, training window and smoothing must participate in the fingerprint. |

Use the same analytical pipeline for pandas/Polars presentation and local/Dask
execution. Semantic `partition_by` is not proof that arbitrary compute
partitions contain a whole game. Validate uniqueness, sequence adjacency,
group totals and join coverage across actual split partitions. Publish
artifacts only after global checks and final schemas pass.

## Implementation order and acceptance evidence

| Order | Deliverable | Required evidence before calling it implemented |
| --- | --- | --- |
| 1 | Shared event/state foundation, Success Rate and raw rushing features | Independent public-interface fixtures; score timing, chronology, attribution and legal boundaries; explicit exclusions, no denominator inflation and zero/unavailable distinctions. Raw Line Yards is an intermediate, not delivered ALY. |
| 2 | Full opponent/situation-adjusted College ALY | Independent joint effect recovery, context standardization, normalization, bipartite rank/prior diagnostics, uncertainty, cutoff isolation and held-out validation. |
| 3 | Own EP model and EPA recipe | Correct scoring/possession/half labels, training-only priors, later-season calibration/support/uncertainty, independently checked EPA and model/checkpoint invalidation. |
| 4 | Dynamic team-strength model and legal matchup simulation | Unit/pace/ST parameter recovery, disjoint score reconciliation, dynamic prior/filter correctness, legal rules, posterior/simulation precision, and held-out accuracy/calibration versus score-only SRS. |

For every product, the eventual tests must use fake external boundaries and
exercise the installed public recipe interface. Include duplicates/conflicts
across partitions, empty/all-null results, partial coverage, deterministic
ordering, failures before publication, cleanup and checkpoint recovery. Verify
all four pandas/Polars by local/Dask combinations at the same semantic revision
with fresh local and Dask executions and actual multipartition task evidence.

Benchmark cold and warm representative small, full-season and skewed inputs.
Record runtime, peak memory, transfer/serialization and shuffle evidence;
inference and fitting costs belong in the report. Small team matrices and
small play samples may be faster locally. Neither parity nor worker placement
supports a distributed-speedup claim by itself.

Implementation acceptance includes `make format` followed by `make check`.
Live profiling, if separately enabled, must use bounded coordinator-owned
requests and quota accounting. The research report itself makes no live-data
coverage, fitted-model quality or runtime-performance claim.
