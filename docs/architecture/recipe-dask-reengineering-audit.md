# Recipe execution audit and native Dask reengineering

- Audit date: October 2, 2026.
- Audited implementation: [`9af6f12493aca6caeb6dbe8dfaaf55927e8691f2`](https://github.com/ryanpaulanderson/cfb-data/tree/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2).
- Coverage: all 13 datasets, three workflows, their helpers, and the shared
  execution, validation, table-operation, and artifact paths.
- Status: historical source audit; native reengineering implemented on the testing branch.
  See [migration verification](native-table-verification.md) for current evidence.
- Governing policy: [product constitution clause IX](../product-constitution.md)
  and [AGENTS.md](https://github.com/ryanpaulanderson/cfb-data/blob/main/AGENTS.md).

## Finding and scope

At the audited commit, every first-party dataset transforms eager lists of Pydantic models.
Dask places eligible functions on workers, but each function processes its
complete inputs in one task. Dictionaries implement joins; lists and sets
implement groups, unions, uniqueness, and coverage checks; Python loops build
new models; Python sorting establishes final order. pandas and Polars are
largely presentation backends for those computations.

This audit identifies an architectural and authoring-quality gap. It does not
assert that all loops are incorrect, that existing validated outputs are wrong,
or that a measured performance regression exists. No performance benchmark
was run for this audit. Existing correctness safeguards must survive migration.

The intended execution model is a lazy Dask DataFrame graph over pandas
partitions, using native projection, filtering, merge, grouping, reduction,
explosion, concatenation, and ordering. Prefer one shared table pipeline with
explicit execution and materialization boundaries, returning dataframe-like
products or explicit named/batched collections. The selected supported result
and execution modes must preserve the same analytical meaning. Dask is
currently an optional installation capability; any packaging change belongs to
the reviewed implementation design. Remote cluster/artifact services are
outside this audit's scope.

There is no backward-compatibility requirement for the existing beta recipe
interfaces. Signatures, schemas, step contracts, and eager/lazy returns may
change when that improves correctness and composition. Existing eager
pandas/Polars returns are observed behavior, not a constraint on the redesign.
Document chosen changes and update examples, tests, semantic revisions, and
artifact compatibility together. Source fidelity, explicit uncertainty,
security, and resource ownership remain requirements. This audit does not
prescribe a particular new public return API or a PyTorch integration; choose
typed dataframe-like outputs/batches that permit later consumers without
reconstructing Python object graphs.

The inventory distinguishes four responsibilities:

| Classification | Meaning | Required treatment |
| --- | --- | --- |
| Table processing | General joins, groups, projections, explosions, concatenations, sorting, and global constraints implemented over complete Python collections. | Replace with native partitioned operations and shared contract checks. |
| Domain rule | Football identity, result, coverage, context, precedence, or null semantics. | Preserve explicitly; use column expressions or a justified bounded partition kernel. |
| Source boundary | Validating and reconciling bounded external responses; conditional HTTP/cap/attempt control. | Keep coordinator ownership; separate bounded response work from downstream table processing. |
| Graph building | Finite, validated parameter expansion and optional-source wiring. | Keep ordinary Python. These loops do not iterate over retrieved data. |

Plain Python functions are compatible with Dask. The problem is the scope and
representation of their work: placing one complete list transform on a worker
does not partition its relational operations. See [Dask Futures](https://docs.dask.org/en/stable/futures.html)
and [Dask DataFrame](https://docs.dask.org/en/stable/dataframe.html).

## Shared engine prerequisites

The recipe changes cannot be completed by exchanging a few loops for pandas
inside the same whole-table function. The current engine recognizes and
materializes tables through model lists. Source links below are fixed to the
audited revision; function names and line ranges identify the actual locations.

| Location | Current behavior and consequence | Required engineering change |
| --- | --- | --- |
| [`_contracts.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data/analytics/_contracts.py): `_table_row_model`, L14–51 | A table step is recognized through `list[Model]` and a declared output model. Other modeled values follow the JSON path. | Introduce a validated table-reference/partition contract with declared schema and grain; retain bounded modeled control values. |
| [`_recipes.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data/analytics/_recipes.py): `StepRecipe._execute_step`, L202–205; `step`, L591–614; `_dataset_declaration`, L676–709 | The callable executes once; the `dask` flag declares placement eligibility. Dataset `partition_by` is stored metadata and datasets are coordinator-placed. | Distinguish native table-graph construction, bounded control tasks, and partition kernels. Expose real compute partitioning separately from storage partition declarations. |
| [`_runtime.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data/analytics/_runtime.py): `_execute_graph`, L264–402 | Retains all completed `_NodeResult.value` objects in the run mapping; executes ready batches with a batch barrier. Node concurrency does not partition rows. | Retain lazy table/artifact references, release unused intermediates, and let native Dask schedule table dependencies within explicit durability boundaries. Evaluate batch barriers separately; do not change source accounting incidentally. |
| [`_execution.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data/analytics/_execution.py): `_NodeResult`, L16–23; `_resolve_arguments`, L26–64; `_resolve_structure`, L67–107 | Passes complete upstream values into each dependent transform. | Bind partitioned table references and scalar controls without gathering the dataset. |
| [`_dask.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data/analytics/_dask.py): `_DaskTransformProvider.execute`, L81–136 | Encodes all parameters, calls `client.submit` once per recipe step, awaits the complete output, and reconstructs a model list. Transfer limits apply to whole inputs/outputs. | Execute collection graphs; transport bounded partitions/references. Keep managed lifecycle, finite concurrency, cancellation, and explicit failure policy. |
| [`_dask_transport.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data/analytics/_dask_transport.py): `_encode_parameters`, L46–101 | Direct `list[Model]` inputs become a complete Arrow IPC payload; optional lists and tuples of lists use modeled JSON. | Use partition schemas and bounded transport for all table input shapes; do not serialize a multi-season tuple as one control payload. |
| Same: `_execute_transform_worker`, L104–157; `_decode_output`, L160–178; `_decode_table_parameter`, L271–280; `_write_ipc`, L283–287; `_read_ipc`, L290–297 | Decodes full inputs, calls one function, validates its full list, writes a complete Arrow payload, then reconstructs the output list on the coordinator. IPC reading uses `read_all`. | Validate and transport bounded partitions. Schema/contract checks remain strict without a full-table model round trip between transformations. |
| [`_transforms.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data/analytics/_transforms.py): `_compute`, L311–338; `_validate_store_and_bind_table`, L340–389 | Calls a whole step or passes through its dataset list, validates all models, constructs full Arrow, and returns the list after storage. | Make partitioned validation and persistence intentional execution boundaries, with coordinator-authorized final publication. |
| Same: `_load_rows`, L726–745; `_validate_dataset_quality`, L971–999; `_dataset_contract`, L1002–1015 | Reconstructs checkpoint rows; global uniqueness uses Python sets and ordering uses complete lists/sorting. `partition_by` is projected into contract metadata. | Restore lazy validated partition references; implement distributed uniqueness/cardinality/order reductions and preserve contract evidence. |
| [`_sources.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data/analytics/_sources.py): `_store_and_bind_rows`, L477–509; `_load_rows`, L515–533 | Builds/stages whole-source Arrow and reconstructs all checkpoint models. | Validate external responses at their boundary, then hand off typed bounded source partitions. A bounded HTTP response may remain eager; composing many responses must not force a dataset-wide gather. |
| [`_artifacts.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data/analytics/_artifacts.py): `_TableArtifactCodec.stage`, L159–250; `load`, L252–326 | Slices an already eager Arrow table into `max_rows_per_part` chunks; staging reloads the parts. Loading reads every part and concatenates them. This is multipart storage, not native compute partitioning or `partition_by` directory partitioning. | Stage bounded validated partitions, aggregate manifest/quality evidence, and publish atomically. Add partition-wise reading/replay/export with a versioned canonical codec; codec/layout changes and explicit incompatible-checkpoint rejection are allowed. |
| [`results.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data/analytics/results.py): `ArtifactRef.load`, L112–126; `export_parquet`, L128–161; `_load_table`, L163–179; `_load_rows`, L181–194 | Eager loading reconstructs models and frames; exporting gathers the table. | Make eager loading explicit where offered; redesign durable execution and partitioned export to avoid mandatory collection. Do not weaken post-client-close resource ownership. |
| [`_runtime.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data/analytics/_runtime.py): `_public_result`, L537–661 | Rematerializes named outputs from lists and scans source lists for coverage/warnings. | Collect only at the explicitly chosen result boundary; propagate bounded coverage diagnostics and descriptors independently from row bodies. |
| [`_tabular.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data/_tabular.py): `_analytics_arrow_table_from_models`, L240–267; `_analytics_models_from_arrow_table`, L291–311; `_analytics_logical_records_from_arrow_table`, L340–366 | Builds full logical/storage record lists and `Table.from_pylist`; reverse conversion calls whole-table `to_pylist` and reconstructs validated models. These allocate the object graphs used by the engine round trips. | Partition-level canonical encoding/validation, including tagged mixed scalars. Schema-column decoding is legitimate boundary work; full-dataset reconstruction between operations is the migration target. |

The original [ADR 0006](0006-modular-analytics-recipes.md) worker contract is
amended by its October 2 execution policy note. Canonical Arrow/Parquet
durability, coordinator authority, and the prohibition on durable pickle remain
in force. Using Dask DataFrames transiently does not require persisting native
DataFrames or changing endpoint result behavior.

### Missing and unsuitable shared operations

The foundation plan's [reusable vocabulary](analytics-foundation-plan.md)
is broader than the implemented table-operation surface:

| Implemented location | Limitation | Required treatment |
| --- | --- | --- |
| [`tabular.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data/analytics/tabular.py): `select_columns`, L38–51; `rename_columns`, L54–77; `strict_cast_columns`, L80–124; `sort_rows`, L127–160 | Provides four eager pandas/Polars operations. `_portable_frame` L163–173 requires `eager_only=True`; `_backend` L208–214 does not accept Dask. Casting converts the full frame to Arrow; sorting assigns a whole-frame stable ordinal. | Provide native lazy equivalents with explicit schemas, lossless casts, stable ordering, and measured partition behavior. The cast loop over schema columns is bounded metadata work, not a problematic row loop. |
| [`operations.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data/analytics/operations.py): `flatten_struct`, L82–146; `explode_list`, L149–239; `_exploded_record`, L242–253 | Iterates logical records/elements and copies dictionaries. Reusing these helpers on complete tables would retain the same execution bottleneck. | Implement typed partition-level structural projection/explosion, preserving collision checks, list-null/empty/element-null distinctions, ordinals, grain changes, and exclusion diagnostics. |
| Same: `nested_value`, L41–79; `_validate_field_name`, L256–258; `_validate_declared_fields`, L261–267; `require_one`, L270–280; `value`, L283–325 | Bounded path/configuration validation and exact-single-row scalar dependencies. | Retain their control/domain responsibilities; do not mistake them for general table scans. |
| No corresponding native composable implementation in the public operation surface | Contract-aware joins and anti-joins, global uniqueness/conflicts, filters with excluded-row evidence, concat, ordered grouping/aggregation, pivot, and identity-evidence joins are performed inside recipes. | Prefer Dask/pandas expressions and thin shared contract-aware adapters. Do not recreate a second generic query engine in Python collections or merely move giant functions into helpers. |

## Complete recipe inventory

Each section links to the immutable audited module. Line ranges include the
function body; decorators may precede them. Models and enums declare contracts,
not generic table engines. All graph builders are separately accounted for.

The preserved semantics below describe source evidence and current domain
policies, not a requirement to keep every existing column or nested output
model. A design may return related child DataFrames instead of lists embedded
in parent rows, avoiding bespoke nested aggregation and large skewed groups.
Keep source identities, relationships, ordinals, nulls, and uncertainty
recoverable, and document any intentional analytical-policy change.

### R01. Recruiting classes

[Source: `recruiting_classes.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data_recipes/recruiting_classes.py).

| Location | Bespoke processing | Native replacement and preserved semantics |
| --- | --- | --- |
| `compose_recruiting_classes`, L78–152; ranking index L89–96 | Dictionary construction and duplicate checks by year/normalized team. | Normalized key columns and global key counts before joins. Preserve ranking-provided display spelling. |
| Same; recruit grouping L98–111 | Recruit-ID set, per-class lists, source spelling precedence. | Global recruit-ID uniqueness, grouped count, and ordered nested-record aggregation. IDs stay strings; missing commitment maps to a distinct uncommitted bucket. |
| Same; union/assembly L113–138 | Set union plus dictionary lookups implement an outer join; per-row models derive status/count. | Full outer merge and explicit status/count expressions. Retain ranking-only zero-count classes, commitments-only teams, uncommitted recruits, and null rank/points. |
| Same; order L139–152 | Whole-result sort and enumeration/model copies assign ordinals. | Declared ordering and global ordinal assignment. Preserve year, uncommitted-last, known-rank-first, rank, key ordering. Current enumeration is global, even though the field description says “within the year”; resolve that semantic mismatch explicitly rather than silently changing it. |
| `_team_key`, L193–194 | Scalar whitespace collapse/casefold and prefix. | Shared typed string expression/kernel retaining Unicode casefold and separation of `team:` keys from `uncommitted`. |

Ordered nested recruits require an order-aware aggregation and skew bound.
Unordered group aggregation or per-partition grouping cannot preserve this
contract when a class spans partitions.

Existing evidence: `test_recipe_recruiting_classes.py` covers union populations,
source/null semantics, duplicate recruit IDs, and four-way canonical parity.
Add class-key duplicates, source-spelling precedence, groups split across
partitions, and deterministic global ordinals. This is the first migration
slice because it exercises grouping, outer merge, nesting, and ordering.

### R02. Player seasons

[Source: `player_seasons.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data_recipes/player_seasons.py).

| Location | Bespoke processing | Native replacement and preserved semantics |
| --- | --- | --- |
| `compose_player_seasons`, L150–326; roster index L178–189 | Complete roster/source-team dictionaries. | Global normalized-team/athlete uniqueness and roster relation. Preserve roster spelling and athlete IDs. |
| Same; statistics L191–216 | Enumeration, duplicate-stat set, identity dictionary, lists of nested statistics. | Global counts by team/athlete/category/type, identity-consistency reduction, ordered statistic aggregation. Wrong seasons and conflicting statistic name/position fail. Preserve original source ordinals, conference, and compound display strings. |
| Same; union/joins L218–260 | Set union plus six full enrichment dictionaries. | Full outer roster/stat membership merge, then declared left joins for usage, PPA, success, passing WEPA, rushing WEPA, and kicker PAAR. Optional evidence cannot expand the universe. |
| Same; row assembly/order L262–326 | Loop, repeated team identity lookup, coverage lookups, model creation, global sort. | Column precedence and coverage expressions; temporal identity evidence relation or bounded kernel. Actual order uses season, casefolded source team, athlete ID; the declaration names raw source team. Reconcile that distinction explicitly. Roster identity wins and roster-only/stats-only athletes survive; absent stats stay explicitly empty. |
| `_identity_text`, L457–458 | Scalar normalized name key. | Preserve exact whitespace/casefold semantics. |
| `_index_enrichment`, L461–492 | Generic index loop with season, duplicate, and universe checks, repeated for six sources. | Shared keyed merge contract with global uniqueness and anti-universe checks. Sparse qualifying-athlete evidence is valid: unmatched requested athletes remain `empty`. |
| `_coverage_for`, L495–507 | Dictionary presence implements requested/matched status. | Explicit request flag and match indicator. `None` means omitted; an empty requested source means `empty`; a match means `present`. |

Keep long-form statistic processing relational until deliberate ordered nested
presentation. Broadcasting temporal team evidence needs a declared small-table
bound; preserve `TeamIdentityIndex` semantics instead of inventing fuzzy matching.

Existing evidence: `test_recipe_player_seasons.py` covers union memberships,
display strings, duplicate statistics, sparse usage, universe isolation, and
four-way parity. Add split athlete groups, cross-partition identity conflicts,
duplicate optional rows, and source-name precedence.

### R03. Team seasons

[Source: `team_seasons.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data_recipes/team_seasons.py).

| Location | Bespoke processing | Native replacement and preserved semantics |
| --- | --- | --- |
| `compose_team_seasons`, L186–347; records L220–225 | Authoritative normalized season/team dictionary. | Records-defined relation and global uniqueness; retain stable team IDs and exactly that row universe. |
| Same; conventional stats L227–249 | Preallocated list groups, enumeration, duplicate set, manual semi-join. | Semi-join to records, matched-key uniqueness, ordered aggregation. Outside-record statistics are currently excluded before duplicate validation. Preserve heterogeneous source scalars and conference/ordinal evidence. |
| Same; advanced stats L251–258 | Semi-join plus dictionary index. | Required merge with matched uniqueness; outside-record rows remain ignored. |
| Same; PPA L260–274 | Index, anti-universe checks, conference checks, complete-key-set comparison. | Global uniqueness, anti-join, context predicate, completeness reduction. Preserve omitted, wholly empty requested, and nonempty incomplete distinctions. |
| Same; optional joins L276–284 and assembly L286–347 | Nine additional optional joins through five helper families, besides inline PPA; numerous lookups, row models, final sort. | Named shared join stages and column coverage expressions. Conventional and advanced statistics are required for each records row; optional sources cannot add records. Order remains season/team ID unless deliberately revised. |
| `_identity_text`, L486–492 | Scalar whitespace/casefold normalization. | Shared exact normalization expression/kernel. |
| `_index_talent`, L495–522 | Name/year index, manual semi-join, complete-set check. | Ignore outside-record rows; reject matched duplicates. A nonempty raw source requires coverage of every records row, even if every returned row is unmatched. Preserve the upstream absence of stable IDs/team filtering. |
| `_index_ats`, L525–556 | Rebuilds records-by-ID, loops source rows, checks names/conferences/coverage. | Stable-ID merge, matched identity predicates, uniqueness and completeness. Ignore unmatched source rows; nonempty raw source requires complete coverage. |
| `_index_returning`, L559–585 | Name-keyed index with strict outside-universe rejection. | Name/year merge plus anti-universe, conference, uniqueness, and nonempty completeness checks. Its unmatched policy differs from ratings. |
| `_index_rating`, L588–621 | Generic dictionary join repeated for CORE/SP+/SRS/Elo/FPI. | Name/year merge; ignore outside-record/aggregate rows, validate reported conference, reject matched duplicates and nonempty partial coverage. |
| `_index_adjusted`, L624–655 | Records-by-ID plus name/conference index loop. | Stable-ID merge; ignore unmatched rows, validate matched name/conference, uniqueness and completeness. |
| `_coverage`, L658–672 | Omitted/present/empty index lookup. | Request and merge-presence expressions with unchanged three-state semantics. |
| `_TeamRating.year`, `.team`, `.conference`, L68–74 | Protocol property declarations, no data processing. | Keep typed contracts; no migration finding. |

The join helpers share mechanics but have different unmatched and completeness
policies. A single permissive default must not erase those differences. Typical
team-season outputs are small; distributed overhead must be measured before
claiming a speed improvement.

Existing evidence: `test_recipe_team_seasons.py` covers records universe,
heterogeneous ordered stats, enrichment parity, required coverage, and empty
requested PPA. Add cross-partition matched duplicates, partial nonempty
enrichments, outside-record policies, and conflicting names/conferences.

### R04. Team games

[Source: `team_games.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data_recipes/team_games.py).

| Location | Bespoke processing | Native replacement and preserved semantics |
| --- | --- | --- |
| `normalize_team_games`, L201–255 | Expands models into a list, performs up to five attachment passes, and sorts all rows. | Home/away projections plus concat and visible join stages. Exactly two perspectives per game survive even with a single-team selector; home ordinal precedes away. |
| `_perspective`, L391–447; `_team_result`, L450–455 | Per-row projection, score arithmetic, nested defaults, conservative result policy. | Column projections and masked expressions. Preserve source completion; unproven results/differentials stay null. Perspective direction and tie behavior remain explicit. |
| `_attach_team_stats`, L458–488 | Nested team loops build a `(game_id, team_id)` index and require a match for each perspective. | Structural explode, global key counts, required left merge, side validation. Duplicate keys anywhere in the returned source fail, including unused rows. Preserve ordered nested stats and `empty` for a matching empty stats list. |
| `_attach_advanced_box`, L491–530 | Checks one exact-game box against two perspectives and copies its nested payload. | Retain bounded exact-game context validation and a small broadcast attachment. Preserve count, team, and score checks and full nested content. This is not a large-table hotspot. |
| `_normalize_team_name`, L533–539 | Scalar normalization. | Exact shared string expression/kernel. |
| `_required_enrichment_keys`, L542–568 | Whole-list set comprehensions and coverage comparisons. | Required-perspective mask and global distinct-key/anti-join reductions. A team selector must resolve in every selected game and cannot remove opponent rows. |
| `_validate_named_enrichment`, L571–596 | Scalar season/week/phase/opponent comparisons. | Explicit column predicates after matching, preserving null semantics. |
| `_attach_advanced_stats`, L599–655 | Base/source dictionaries, duplicate/outside checks, subset coverage, model copying. | Declared name/game left merge, global uniqueness/anti-universe/required-coverage checks, context predicates, coverage assignment. |
| `_attach_havoc`, L658–721 | Repeats join machinery with team/opponent conference checks. | Same shared mechanics with these additional explicit predicates. |
| `_attach_ppa`, L724–782 | Repeats join machinery with team conference checks. | Same shared mechanics with its own context and coverage policy. |

For advanced statistics, havoc, and PPA, nonempty source responses must cover
every required perspective. A wholly empty requested response produces `empty`
for required perspectives and `not_requested` for unselected ones. A generic
“all missing joins fail” policy would change current behavior.

Existing evidence: `test_recipe_team_games.py` covers two conservative base
perspectives, enrichments, incomplete conventional stats, selected-perspective
empty coverage, conflicting context, and exact-box/PPA selector planning.
Add global duplicate and required-perspective checks split across partitions.

### R05. Rosters

[Source: `rosters.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data_recipes/rosters.py).

| Location | Bespoke processing | Native replacement and preserved semantics |
| --- | --- | --- |
| `normalize_roster`, L105–122 | Builds a full temporal team index, maps every player to a model, then sorts. | Projection and explicit identity-evidence join/bounded partition kernel. Actual sorting uses season, casefolded source team, athlete ID while the declaration names raw source team; reconcile intentionally. Team evidence may be broadcast only under an explicit bound. |
| `_normalize_player`, L154–181 | Scalar identity lookup and field-by-field model construction. | Project fields and attach evidence columns. Preserve resolved/unresolved/ambiguous status, null unresolved team IDs, candidate order, exact source team, and nested recruit-ID order. |

Existing evidence: `test_recipe_rosters.py` covers identity ambiguity,
candidate/recruit order, duplicate memberships, and parity. Add normalized
alias collisions and duplicates across partitions without dropping unresolved
memberships.

### R06. Game summaries

[Source: `game_summaries.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data_recipes/game_summaries.py).

| Location | Bespoke processing | Native replacement and preserved semantics |
| --- | --- | --- |
| `normalize_games`, L258–268 | Whole-list projection plus sort. | Native projection/rename, masked derivation, declared order. Retain future/incomplete/completed games and nested source fields. |
| `select_exact_game_media`, L277–292 | Python filter of a complete media response. | Boolean game-ID filter preserving source-relative order. The endpoint still lacks an exact-game selector; do not claim narrower source retrieval. |
| `attach_game_enrichments`, L301–320 | Encapsulates both whole-list joins in one step. | Expose media/weather joins and coverage as separate named transformations. |
| `_normalize_game`, L449–491; `_result`, L494–505 | Row-model mapping and scalar result arithmetic. | Projection and completion/non-null score masks. Scores become outcomes only when completion and both values support them; ties retain null winner/loser IDs. |
| `_attach_media`, L508–555 | Game dictionary, duplicate set, grouped lists, context checks, model-copy loop. | Global uniqueness by game/type/outlet; anti-universe/context checks; ordered grouping and left merge. Preserve every base game and every broadcast, including valid-empty versus omitted coverage. |
| `_attach_weather`, L558–609 | Game/weather dictionaries, duplicate/context/venue checks, model-copy loop. | Global game-ID uniqueness, anti-universe/context validation, many-to-one left merge. Preserve known base venue evidence and requested-empty states. |
| `_validate_game_enrichment`, L612–657 | Rowwise context comparisons. | Shared column checks with explicit null semantics for season/week/phase/instant/team/conference evidence. Conference comparisons conflict only when both values are known. |
| `_normalized_team`, L660–666 | Scalar whitespace collapse and Unicode casefold. | Exact vectorized normalization or bounded typed kernel; `lower()` alone is not equivalent. |

Existing evidence: `test_recipe_game_summaries.py` covers conservative outcomes,
exact-game media selection, weather, empty enrichments, duplicate media,
selector rejection, and parity. Add duplicate/unmatched/context/venue conflicts
crossing partitions.

### R07. Player-game statistics

[Source: `player_game_stats.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data_recipes/player_game_stats.py).

| Location | Bespoke processing | Native replacement and preserved semantics |
| --- | --- | --- |
| `flatten_player_game_stats`, L81–147; context L92–96 | Unique game-context dictionary. | Global game-context uniqueness and declared context merge; missing context must fail explicitly. |
| Same; flatten L98–135 | Five-level game/team/category/type/athlete loops, ordinal enumeration, model construction. | Successive typed structural explosions with parent ordinals captured before repartitioning, then projection/context merge. Preserve home/away-derived stable team IDs/classification, leading-zero athlete IDs, compound strings, and repeated athletes in distinct stat types. |
| Same; order L136–147 | Whole-result Python sorting. | Declared global source-aware order and candidate-key checks. Empty child lists produce no observations; native explode placeholder rows must not become athletes. |

Existing evidence: `test_recipe_player_game_stats.py` covers perspective IDs,
display strings, duplicate candidate keys, and parity. Add empty nested levels,
missing/duplicate game context, and ordinal/key checks across partitions.

### R08. Drives

[Source: `drives.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data_recipes/drives.py).

| Location | Bespoke processing | Native replacement and preserved semantics |
| --- | --- | --- |
| `normalize_drives`, L119–139 | Python exact-game filter, per-row projection, whole-result sort. | Filter/project/assign/order. Drive numbers remain null-last with drive-ID tie-breaking. |
| `_clock_seconds`, L197–200 | Scalar clock arithmetic. | Masked `minutes * 60 + seconds`, null unless both components are known. Preserve source clocks independently. |
| `_normalize_drive`, L203–235 | Per-row field mapping/model construction and score/clock arithmetic. | Native projection and expressions preserving start/end/elapsed clocks and direct score differences. Add no implicit drive-success definition. |

Existing evidence: `test_recipe_drives.py` covers clocks, direct arithmetic,
post-retrieval exact-game filtering, duplicate keys, selectors, and parity.
Add null sequence ordering and ties across partitions.

### R09. Plays

[Source: `plays.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data_recipes/plays.py).

| Location | Bespoke processing | Native replacement and preserved semantics |
| --- | --- | --- |
| `normalize_plays`, L133–144 | Predicate generator, per-row model mapping, sorting. | Boolean filtering, projection, masked arithmetic, order. Nullable source PPA remains unknown. |
| `attach_win_probability`, L153–185 | Base IDs, duplicate set, probability dictionary, game checks, exact-cover set equality, lookup reconstruction. | Global uniqueness, correct-game predicates, anti-joins in both directions to prove exact coverage, then one-to-one merge. Missing and extra probabilities both fail; base plays cannot be dropped. |
| `_clock_seconds`, L256–259; `_normalize_play`, L262–302 | Scalar clock/null policy, field projection, probability-state assignment. | Masked clock expressions and native column assignments preserving nested values and omitted enrichment semantics. |
| `_sort_rows`, L305–316 | Eager sorting by game, nullable drive/play numbers, play ID. | Explicit global ordering, null-last sequence numbers, ID tie-breaker. Partition-local sort alone is insufficient. |

Existing evidence: `test_recipe_plays.py` covers nullable PPA/clocks, no default
probability fetch, incomplete probability coverage, exact-game selection, and
enriched parity. Add extra/duplicate/wrong-game probabilities and split-key
exact-cover checks.

### R10. Betting lines

[Source: `betting_lines.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data_recipes/betting_lines.py).

| Location | Bespoke processing | Native replacement and preserved semantics |
| --- | --- | --- |
| `flatten_betting_lines`, L95–135 | Nested game/quote loop, per-parent enumeration/model construction, eager sorting. | Typed quote explosion with source ordinal, parent projection, declared order. Preserve all providers, raw spread labels, open/current nulls, and zero rows for empty quote lists. Do not choose consensus, closing, or ATS semantics. |

Existing evidence: `test_recipe_betting_lines.py` covers every quote, null/raw
values, duplicate game/provider/ordinal keys, and parity. Add empty quote lists
and cross-partition duplicate/source-order checks.

### R11. Poll rankings

[Source: `poll_rankings.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data_recipes/poll_rankings.py).

| Location | Bespoke processing | Native replacement and preserved semantics |
| --- | --- | --- |
| `flatten_poll_rankings`, L62–99 | Snapshot/poll/rank loops, two ordinal enumerations, row models, eager sorting. | Typed poll then rank explosion and field projection, retaining per-parent ordinals. Preserve source rank order separately from numeric rank, null rank/votes/points/final evidence, and zero rows for empty lists. |

Existing evidence: `test_recipe_poll_rankings.py` covers source order, nulls,
duplicate snapshot keys, and parity. Add duplicate season/phase/week/poll/team
keys across partitions; do not fill missing ranks or reorder by numeric rank.

### R12. Coach seasons

[Source: `coach_seasons.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data_recipes/coach_seasons.py).

| Location | Bespoke processing | Native replacement and preserved semantics |
| --- | --- | --- |
| `normalize_coach_seasons`, L103–109 | Full-list projection and sorting. | Native projection and order, retaining nested identity/attribution evidence. |
| `attach_tenure_context`, L118–142 | Scans every tenure for each coach-season row, then requires exactly one match. | Key merge by coach/team plus inclusive year-interval predicate and global match-count reduction. Preserve zero-match and multiple-match failures, null open-ended years, and base rows before checking coverage. Control candidate-join skew. |
| `_normalize_season`, L195–245 | Per-row flattening/model construction and optional tenure/coverage fields. | Native projection/assign after validated matching. Preserve partial-record attribution and source context; do not infer profile linkage. |
| `_sort_rows`, L248–249 | Eager year/team/coach sort. | Declared deterministic global order. |

The nested tenure scan has work proportional to season rows times tenure rows
in the current source. This is an algorithmic observation, not a timing result.

Existing evidence: `test_recipe_coach_seasons.py` covers optional nested/tenure
context, no profile fetch, missing requested tenure, and parity. Add ambiguous
matches, inclusive boundaries, open tenures, and split-partition candidates.

### R13. Play-player statistics

[Source: `play_player_stats.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data_recipes/play_player_stats.py).

| Location | Current responsibility | Required treatment and preserved semantics |
| --- | --- | --- |
| `PlayPlayerStatRow.validate_coverage`, L36–46 | Scalar model invariant: warning agrees with complete/partial state. | Keep strict boundary validation and equivalent partition predicates. |
| `_stat_limit`, L49–54; `_validate_game`, L57–74; `_candidate_key`, L118–120; `_validate_types`, L179–189 | Descriptor lookup, one-game validation, key projection, small vocabulary checks. | Retain bounded coordinator control/domain work. The descriptor remains the authoritative cap owner. |
| `_validate_rows`, L77–115 | Per-response set and row loop validate season/week/game/participants/stat type and duplicate associations. | Keep strict bounded external-response validation; do not move authenticated retrieval to workers. Downstream dataset-wide checks still need distributed reductions. |
| `_observed_union`, L123–140 | Dictionary reconciliation of overlapping adaptive responses, with full row equality. | Preserve conflict-failing, association-keyed reconciliation within declared response/attempt bounds. A reused mechanism may become a shared conflict-aware union; ordinary deduplication choosing an arbitrary winner would be incorrect. |
| `_with_coverage`, L143–161 | Reconstructs each response model to attach coverage/warning. | Use table assignments after boundary validation where practical; preserve complete/partial warning semantics. This bounded response operation is lower priority than whole-dataset merges. |
| `_require_parent_covered`, L164–176 | Serializes parent/child rows into sets to prove containment. | Preserve adaptive provenance check; key/equality anti-join is the table equivalent. Do not weaken equality or discard contradictions. |
| `_complete_game`, L199–268 | Coordinator HTTP state machine: exact game, two participant partitions, then authoritative stat-type partitions; accumulation and attempt-budget handling. | Retain finite typed endpoint allowlist, cache/session/attempt policy, conditional retrieval, and validated partial output. Separate bounded source reconciliation from native downstream transforms. No mechanical worker fan-out of requests. |
| `_merge_games`, L272–285 | Concatenates tuples of complete per-game lists, then globally sorts. | Lazy table concat and declared ordering; this is the principal native-table migration target in this module. Tuple-list transport also requires the engine prerequisite above. |

Existing evidence: `test_recipe_play_player_stats.py` covers cap partitioning,
identity/context/duplicate/conflict checks, attempts, partial warnings, and
checkpoint exclusion. Preserve validated partial rows when a leaf stays capped
or the budget ends; malformed or contradictory responses still fail. Add
multipartition multi-game concat/order and partial/complete metadata parity.

### W01. Program history

[Source: `program_history.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data_recipes/program_history.py).

| Location | Current responsibility | Required treatment |
| --- | --- | --- |
| `_concatenate_game_summaries`, L48–52; `_concatenate_team_games`, L61–65; `_concatenate_team_seasons`, L74–78; `_concatenate_recruiting_classes`, L87–91; `_concatenate_poll_rankings`, L100–104 | Five `dask=False` coordinator steps delegate complete season lists to `_concatenate`. | Native concat of lazy table references/partitions; preserve season sequence and each child's source/order/contract. No whole multi-season gather for durable execution. |
| `_concatenate`, L257–258 | Nested list comprehension copies every season's rows into one list. | Shared native concat with explicit row-universe and ordering checks. |
| `program_history`, L108–245; `_seasons`, L248–254 | Validates and expands an inclusive range of at most 50 seasons during compilation. Tuple comprehensions create graph references. | Keep bounded graph construction and aliases. Table graph construction must remain no-I/O; no source-derived request fan-out. |

Existing evidence: `test_recipe_program_history.py` covers bounded planning,
source sharing, output semantics, and parity. Add native concatenation across
multiple seasons/partitions with an artifact path that never collects the
whole history, while preserving child recovery and ordered presentation.

### W02–W03. Team-season and single-game workflows

[Source: `team_season_analysis.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data_recipes/team_season_analysis.py)
and [source: `single_game_analysis.py`](https://github.com/ryanpaulanderson/cfb-data/blob/9af6f12493aca6caeb6dbe8dfaaf55927e8691f2/cfb_data/cfb_data_recipes/single_game_analysis.py).

`team_season_analysis`, L38–175, and `single_game_analysis`, L36–89, already
perform declarative composition and named-output wiring. They contain no
custom row-processing kernels. Migrate referenced table types/contracts and
verify child graph composition. Keep the single-game `require_one`/`value`
exact-row scalar dependency, L63–66; it is bounded control work.

Existing evidence: `test_recipe_team_season_analysis.py` and
`test_recipe_single_game_analysis.py` cover named outputs, deduplicated sources,
selectors, and parity. Add actual partitioned child execution and independently
recoverable output evidence.

### All dataset builders and package files

These builders contain source calls, optional-source branches, and selector
validation rather than runtime data loops. They need to compose the new table
stages, but their ordinary Python control flow is appropriate:

| Module | Builder and audited lines |
| --- | --- |
| `recruiting_classes.py` | `recruiting_classes`, L164–190 |
| `player_seasons.py` | `player_seasons`, L338–454 |
| `team_seasons.py` | `team_seasons`, L359–483 |
| `team_games.py` | `team_games`, L268–388 |
| `rosters.py` | `rosters`, L134–151 |
| `game_summaries.py` | `game_summaries`, L333–446; bounded selector `any` expressions are planning logic. |
| `player_game_stats.py` | `player_game_stats`, L168–210 |
| `drives.py` | `drives`, L151–194 |
| `plays.py` | `plays`, L198–253 |
| `betting_lines.py` | `betting_lines`, L148–185 |
| `poll_rankings.py` | `poll_rankings`, L118–146 |
| `coach_seasons.py` | `coach_seasons`, L154–192 |
| `play_player_stats.py` | `play_player_stats`, L297–318; explicit positive unique game IDs and finite compile-time expansion. |

`__init__.py` is only a package docstring and `py.typed` is a typing marker.
Neither contains a transformation. The inventory accounts for all 22 `@step`
functions, 45 undecorated top-level helpers, one adaptive source, 13 dataset
builders, three workflow builders, the coverage validator, and the three
rating protocol properties in the audited recipe package.

## Native execution and semantic constraints

Implementing a lazy graph is necessary but insufficient. The migration must
address the following explicitly:

1. **Partitioned inputs and strict metadata.** Derive metadata from declared
   schemas, including typed empty/all-null and nested fields, without calling
   source or transform code for inference. Do not construct one giant pandas
   frame and partition it after all processing has finished.
2. **Global invariants.** Uniqueness, conflicts, join cardinality, completeness,
   and outside-universe checks need distributed reductions or anti-joins. A
   partition-local set cannot catch duplicate keys in different partitions.
3. **Native joins and reductions.** Use indexed/broadcast joins when evidence
   and bounds justify them; otherwise plan an explicit shuffle. Use native
   aggregations where possible. A partition map does not colocate a complete
   logical group. See [Dask joins](https://docs.dask.org/en/stable/dataframe-joins.html)
   and [grouping/shuffling](https://docs.dask.org/en/stable/dataframe-groupby.html).
4. **Ordered nested data or child tables.** Carry source ordinals before
   explosion/shuffling. Return normalized child tables with explicit relations
   or deliberately reassemble typed records in source order. Define a skew bound
   for a single class/athlete group. Dask `Object`/string inference and pandas explosion of
   empty lists must not change nested contents or fabricate rows. Preserve
   heterogeneous Stats scalars through the established tagged codec.
5. **Ordering and ordinals.** Distinguish storage/compute partitions from
   declared analytical order. Sorting each partition is not a global sort.
   Partition offsets/global ordering must preserve existing ordinals and tie
   breakers without relying on scheduler arrival order.
6. **Domain kernels.** A necessary structural or identity kernel may use a
   bounded pandas partition with explicit `meta`, null/cardinality/order
   semantics, and validated dimension bounds. Small functions/lambdas may
   supply explicit business rules without reimplementing general table
   mechanics. A kernel cannot secretly fetch data,
   gather other partitions, or replace a native join/group with row-wise
   `apply`. See [Dask `map_partitions`](https://docs.dask.org/en/stable/generated/dask.dataframe.DataFrame.map_partitions.html).
7. **Durability and recovery.** Validate partitions and global evidence before
   atomic authoritative publication. Stage/replay/export bounded Arrow/Parquet
   parts; preserve fail-closed corruption behavior and crash cleanup. Separate
   implementation/execution compatibility from semantic revisions; change
   semantic revisions when meaning changes, and invalidate incompatible
   checkpoints without reusing unverified execution evidence.
8. **Planning and observation.** The recipe plan remains pure and no-I/O.
   Native execution partitioning may be determined at runtime from declared
   inputs; this does not authorize new source requests. Explain operations,
   shuffles, partitions, validation, and collection boundaries without logging
   payloads/secrets. Preserve budgets, source deduplication, cancellation, and
   partial-source checkpoint exclusion.
9. **Explicit collection and beta returns.** Current direct calls promise an
   eager frame and therefore collect. The redesigned interface may return lazy
   dataframe-like products, named frames, or batches instead. Choose the most
   correct usable contract; do not preserve the eager/list architecture for
   compatibility. Durable execution must not require eager loading merely to
   return artifacts, coverage, and lineage. Document any new API and its
   resource lifetime; future PyTorch consumers should receive typed table/batch
   boundaries, not incidental Pydantic object graphs.

## Reengineering sequence

This is the implementation work queue for this audit. No runtime migration or
new dependency is performed by the documentation change.

| Phase | Scope | Acceptance gate |
| --- | --- | --- |
| 1. Execution contract | Lazy table references, native Dask collection execution, a shared pipeline for supported modes, partition metadata, distributed validation, bounded artifact staging/replay, explicitly chosen dataframe-like return/collection contract. | A public minimal recipe processes genuinely separate partitions, validates its chosen schema/quality/lineage, and completes a durable artifact run without a whole-table list round trip. Breaking beta API changes are allowed. |
| 2. Recruiting vertical slice | R01 normalization, global uniqueness, ordered grouped recruits/counts, outer merge, status, order/ordinals. | Existing semantics plus split-key/group, empty/null, skew, and performance evidence. Use native APIs/thin adapters, not a new collection-based query engine. |
| 3. Shared joins and composition | R05 rosters; R02 player seasons; R03 team seasons; R04 team games; R06 game summaries. | All source-specific unmatched/completeness/identity policies remain explicit; named operations are visible; reusable mechanics eliminate duplicated dictionaries/set comparisons. |
| 4. High-volume structural paths | R07 player-game stats; R08 drives; R09 plays; R10 betting; R11 polls; R12 coaches. | Typed explosions, cross-partition exact cover and tenure matching, order fidelity, and meaningful nested/large-data benchmarks. |
| 5. Multi-output/history and capped data | R13 downstream merging, W01 concat, W02/W03 composition; bounded adaptive source remains coordinator-owned. | Multi-season/game graphs do real partition work; source budgets/partial warnings and independent recovery are unchanged. |
| 6. Closure | Every inventory entry, source guide, architecture status, examples, packaging, and executor/result matrix. | Required checks plus benchmark report; explicitly close each target or document a justified bounded domain/control role. No remaining undocumented whole-table Python engine. |

Architecture and dependency choices within phase 1 need a concrete design
before implementation, including the chosen beta return contract. This audit
records the work and acceptance evidence; runtime reengineering remains pending.

## Verification and performance evidence

The existing `test_recipe_*.py` tests exercise public recipes, source contracts,
logical outputs, failure cases, and canonical pandas/Polars by local/Dask
parity. Their small one-worker fixtures are valuable regression evidence.
They do not establish native DataFrame execution, cross-partition correctness,
bounded large-table memory, or speed.

Each migrated recipe needs independently computed outputs with checkpoint
reuse disabled so a replay cannot masquerade as execution. For the same new
semantic revision, supported modes must agree on canonical schema, values,
nulls, nesting, row/column order, errors, coverage, warnings, and source attempt
counts. Existing tests provide a semantic baseline, not a prohibition on
intentional beta schema/API changes. Document any changed analytical policy
and reject incompatible artifacts rather than silently reusing them.
Add deliberate adversarial fixtures:

- Split matching keys, duplicate keys, conflicting evidence, and complete
  groups across two or more input partitions.
- Exercise unmatched-left/right, empty requested versus omitted sources,
  partial nonempty sources, null keys, name collisions, and temporal ambiguity.
- Check empty/null nested lists, element nulls, leading-zero string IDs,
  heterogeneous stats, source-ordinal ties, and groups larger than typical
  partitions.
- Test global uniqueness/order validation and atomic publication failure when
  a late partition is invalid; preserve cancellation and worker-failure cleanup.
- Record optimized collection/task and partition evidence that multiple input
  partitions performed actual transformation work. Exact task counts need not
  be stable across Dask optimizer versions. Merely seeing a worker PID, a
  `dask` placement event, or multiple artifact files is insufficient.

Use deterministic synthetic fixtures shaped like the real source contracts;
large-data benchmarking does not require live network calls. Compare the
audited list implementation, native local pandas, and native Dask using the
same semantics and hardware. Include a small notebook-sized case, increasing
flat/high-volume play data, deep nested data, and skewed class/athlete groups.
Run more than one partition and worker setting within available resources.

Record input/output rows and bytes, partition sizes/counts, worker count,
dependency versions, cold cluster startup, warm execution, validation and
artifact time, serialization/transfer/shuffle volume, and peak coordinator and
worker memory. Separate cold computation, response-cache warmth, and checkpoint
replay. Report repeated-run summaries and the small-data crossover; define
measurable runtime/memory budgets before claiming improvement. Dask scheduling
and shuffles have costs, and small in-memory pandas workloads may be faster.
See [Dask performance guidance](https://docs.dask.org/en/stable/dataframe-best-practices.html).

Implementation acceptance remains `make format`, then `make check`, with
additional partition/runtime benchmarks appropriate to the migrated paths.
Redis/live tests are separate opt-in verification and are unnecessary for this
source-only documentation audit.
