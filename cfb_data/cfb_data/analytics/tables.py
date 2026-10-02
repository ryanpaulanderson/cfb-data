"""Compose validated analytical tables through native dataframe operations."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Final, Literal

import narwhals.stable.v2 as nw
import pandas as pd
from narwhals.stable.v2.typing import IntoLazyFrame

from .errors import CFBDTransformError

type JoinCardinality = Literal[
    "one_to_one", "many_to_one", "one_to_many", "many_to_many"
]
type JoinKind = Literal["inner", "left", "full", "semi", "anti", "cross"]
type PartitionFunction = Callable[[pd.DataFrame], pd.DataFrame]

SOURCE_ORDINAL: Final = "__cfb_source_ordinal"


@dataclass(frozen=True, slots=True)
class _TableCheck:
    """Bind a global invalid-row count to its safe failure message."""

    frame: nw.LazyFrame[IntoLazyFrame]
    message: str


def _merge_checks(*groups: tuple[_TableCheck, ...]) -> tuple[_TableCheck, ...]:
    """Retain each inherited check once when graph branches reconverge."""
    checks: dict[int, _TableCheck] = {}
    for group in groups:
        for check in group:
            checks.setdefault(id(check), check)
    return tuple(checks.values())


@dataclass(frozen=True, slots=True)
class _EnrichmentUniverse:
    """Retain the original key relation across universe-preserving enrichments."""

    keys: tuple[str, ...]
    frame: nw.LazyFrame[IntoLazyFrame]


@dataclass(frozen=True, slots=True)
class Table:
    """Carry a native dataframe graph and deferred global validation.

    Operations preserve inherited checks and do not perform computation.
    ``frame`` exposes the native Narwhals expression interface. Computation
    and artifact publication are owned by the recipe execution engine.

    :param frame: Lazy native dataframe graph with declared column metadata.
    """

    frame: nw.LazyFrame[IntoLazyFrame]
    _checks: tuple[_TableCheck, ...] = ()
    _universe: _EnrichmentUniverse | None = None
    _known_empty: bool = False

    @property
    def columns(self) -> tuple[str, ...]:
        """Return declared columns without evaluating the graph."""
        return tuple(self.frame.collect_schema().names())

    def select(self, *expressions: str | nw.Expr) -> Table:
        """Project expressions while preserving inherited validation.

        :param expressions: Explicit named columns or native expressions.
        :return: Projected table without executing its graph.
        """
        return replace(
            self,
            frame=self.frame.select(*expressions),
            _universe=None,
            _known_empty=self._known_empty
            if all(isinstance(expr, str) for expr in expressions)
            else False,
        )

    def with_columns(self, *expressions: nw.Expr) -> Table:
        """Assign native column expressions without collecting rows.

        :param expressions: Native expressions with explicit output names.
        :return: Table with assigned columns and inherited checks.
        """
        return replace(
            self, frame=self.frame.with_columns(*expressions), _universe=None
        )

    def filter(self, predicate: nw.Expr) -> Table:
        """Filter rows with an explicit null-as-false predicate.

        :param predicate: Boolean expression; null observations are excluded.
        :return: Filtered native table.
        """
        return replace(
            self, frame=self.frame.filter(predicate.fill_null(False)), _universe=None
        )

    def rename(self, names: Mapping[str, str]) -> Table:
        """Rename columns without allowing collisions.

        :param names: Existing names mapped to unique output names.
        :return: Renamed native table.
        :raises CFBDTransformError: If columns are absent or collide.
        """
        targets = tuple(names.get(name, name) for name in self.columns)
        if not set(names) <= set(self.columns) or len(set(targets)) != len(targets):
            raise CFBDTransformError("Table rename columns are unavailable or collide")
        return replace(self, frame=self.frame.rename(dict(names)), _universe=None)

    def drop(self, *names: str) -> Table:
        """Remove explicitly named columns.

        :param names: Existing columns to remove.
        :return: Projected table with inherited validation.
        """
        return replace(
            self,
            frame=self.frame.drop(*names),
            _universe=self._universe
            if self._universe is not None
            and not set(names).intersection(self._universe.keys)
            else None,
        )

    def require(self, predicate: nw.Expr, *, message: str) -> Table:
        """Require a predicate globally before publishing any result.

        :param predicate: Boolean invariant; null counts as a violation.
        :param message: Safe error message without row values.
        :return: Table carrying a deferred distributed invalid-row reduction.
        """
        invalid = (
            self.frame.with_columns(
                predicate.fill_null(False)
                .cast(nw.Boolean)
                .alias("__cfb_contract_predicate")
            )
            .filter(nw.col("__cfb_contract_predicate") == nw.lit(False))
            .select(nw.len().alias("invalid_count"))
        )
        return replace(self, _checks=(*self._checks, _TableCheck(invalid, message)))

    def require_unique(self, keys: Sequence[str], *, message: str) -> Table:
        """Require non-null globally unique candidate keys.

        :param keys: Explicit candidate-key columns.
        :param message: Safe failure message.
        :return: Table carrying null-key and cross-partition duplicate checks.
        :raises CFBDTransformError: If keys are absent or duplicated.
        """
        selected = tuple(keys)
        if not selected or len(set(selected)) != len(selected):
            raise CFBDTransformError("Candidate keys must be non-empty and unique")
        if not set(selected) <= set(self.columns):
            raise CFBDTransformError("Candidate-key columns are unavailable")
        nonnull = nw.all_horizontal(
            *(~nw.col(key).is_null() for key in selected), ignore_nulls=False
        )
        checked = self.require(nonnull, message=message)
        duplicates = (
            self.frame.group_by(*selected)
            .agg(nw.len().alias("__key_count"))
            .filter(nw.col("__key_count") > 1)
            .select(nw.len().alias("invalid_count"))
        )
        return replace(
            checked, _checks=(*checked._checks, _TableCheck(duplicates, message))
        )

    def join(
        self,
        other: Table,
        *,
        on: Sequence[str] = (),
        how: JoinKind = "left",
        cardinality: JoinCardinality = "many_to_one",
        suffix: str = "_right",
        message: str = "Join candidate keys are not unique",
    ) -> Table:
        """Join native tables with explicit global cardinality checks.

        :param other: Right table with inherited validation.
        :param on: Shared key columns; empty only for an explicit cross join.
        :param how: Native join strategy.
        :param cardinality: Required key multiplicity on each side.
        :param suffix: Suffix applied to colliding right columns.
        :param message: Safe multiplicity failure message.
        :return: Joined native table carrying both input contracts.
        :raises CFBDTransformError: If join configuration is invalid.
        """
        keys = tuple(on)
        if how != "cross" and not keys:
            raise CFBDTransformError("A keyed join requires explicit columns")
        left = self
        right = other
        if how != "cross":
            if cardinality in {"one_to_one", "one_to_many"}:
                left = left.require_unique(keys, message=message)
            if cardinality in {"one_to_one", "many_to_one"}:
                right = right.require_unique(keys, message=message)
        frame = left.frame.join(
            right.frame, on=list(keys) if keys else None, how=how, suffix=suffix
        )
        if how == "full":
            available = set(frame.collect_schema().names())
            retained = tuple(key for key in keys if f"{key}{suffix}" in available)
            if retained:
                frame = frame.with_columns(
                    *(
                        nw.coalesce(nw.col(key), nw.col(f"{key}{suffix}")).alias(key)
                        for key in retained
                    )
                ).drop(*(f"{key}{suffix}" for key in retained))
        return Table(
            frame,
            _merge_checks(left._checks, right._checks),
            _known_empty=left._known_empty
            if how in {"left", "inner", "semi", "anti"}
            else left._known_empty and right._known_empty,
        )

    def aggregate(
        self, *, keys: Sequence[str], expressions: Sequence[nw.Expr]
    ) -> Table:
        """Aggregate groups using native distributed reductions.

        :param keys: Explicit group columns.
        :param expressions: Native aggregation expressions with output names.
        :return: Grouped table carrying inherited validation.
        """
        return replace(
            self, frame=self.frame.group_by(*keys).agg(*expressions), _universe=None
        )

    def distinct(self, *keys: str) -> Table:
        """Project and deduplicate only explicit key evidence.

        :param keys: Columns whose identical observations represent one key.
        :return: Distinct key relation without choosing a payload winner.
        """
        return replace(
            self,
            frame=self.frame.select(*keys).unique(subset=list(keys)),
            _universe=None,
        )

    def enrich(
        self,
        source: Table | None,
        *,
        on: Sequence[str],
        output: str,
        coverage: str,
        fields: Mapping[str, str],
        outside: Literal["reject", "ignore"] = "reject",
        completeness: Literal["required", "if_nonempty", "sparse"] = "sparse",
        message: str,
    ) -> Table:
        """Attach one declared keyed enrichment without expanding base rows.

        :param source: Requested native source or ``None`` when omitted.
        :param on: Shared identity keys already normalized by domain code.
        :param output: Nested source-record output column.
        :param coverage: Explicit requested/present/empty status column.
        :param fields: Source fields retained in the nested source record.
        :param outside: Whether source rows outside the base universe fail.
        :param completeness: Required, nonempty-required, or sparse matching.
        :param message: Safe source-specific failure context.
        :return: Base universe with native joins and global validation.
        """
        if outside not in {"reject", "ignore"} or completeness not in {
            "required",
            "if_nonempty",
            "sparse",
        }:
            raise CFBDTransformError("Enrichment coverage policy is invalid")
        if source is not None and (
            not fields
            or not set(fields) <= set(source.columns)
            or not set(on) <= set(source.columns)
            or len(set(fields.values())) != len(fields)
        ):
            raise CFBDTransformError(
                "Enrichment fields or keys are unavailable or collide"
            )
        keys = tuple(on)
        if (
            not keys
            or not set(keys) <= set(self.columns)
            or output in keys
            or coverage in keys
        ):
            raise CFBDTransformError(
                "Enrichment requires available keys and separate payload columns"
            )
        if source is None:
            return replace(
                self.with_columns(
                    nw.lit(None).alias(output), nw.lit("not_requested").alias(coverage)
                ),
                _universe=self._universe,
            )
        if source._known_empty:
            checked = source.require_unique(keys, message=message)
            result = replace(
                self.with_columns(
                    nw.lit(None).alias(output), nw.lit("empty").alias(coverage)
                ),
                _checks=_merge_checks(self._checks, checked._checks),
                _universe=self._universe,
            )
            return (
                result.require(nw.lit(False), message=message)
                if completeness == "required"
                else result
            )
        universe = self._universe
        if universe is None or not set(keys) <= set(
            universe.frame.collect_schema().names()
        ):
            universe = _EnrichmentUniverse(keys, self.frame)
        marker = f"__{output}_matched"
        base_keys = Table(
            universe.frame.select(*keys).unique(subset=list(keys)), self._checks
        )
        base_keys = base_keys.require_unique(keys, message=message)
        extra = source.join(base_keys, on=keys, how="anti", cardinality="many_to_many")
        inherited = source._checks
        if outside == "reject":
            extra = extra.require(nw.lit(False), message=message)
            inherited = _merge_checks(inherited, extra._checks)
        matched = source.join(
            base_keys, on=keys, how="semi", cardinality="many_to_many"
        ).require_unique(keys, message=message)
        payload = (
            matched.pack(columns=fields, into=output)
            .with_columns(nw.lit(True).alias(marker))
            .select(*keys, output, marker)
        )
        # Packing and explicit projection retain the source's globally checked keys.
        joined = Table(
            self.frame.join(payload.frame, on=list(keys), how="left"),
            _merge_checks(self._checks, payload._checks, inherited),
        )
        if completeness != "sparse":
            missing = base_keys.join(
                matched.distinct(*keys), on=keys, how="anti", cardinality="many_to_many"
            )
            counts = Table(
                missing.frame.select(nw.len().alias("__missing_rows")), missing._checks
            )
            predicate = nw.col("__missing_rows") == 0
            if completeness == "if_nonempty":
                size = Table(source.frame.select(nw.len().alias("__source_rows")))
                counts = counts.join(size, how="cross", cardinality="many_to_many")
                predicate = predicate | (nw.col("__source_rows") == 0)
            counts = counts.require(predicate, message=message)
            joined = replace(
                joined, _checks=_merge_checks(joined._checks, counts._checks)
            )
        result = joined.with_columns(
            nw.when(nw.col(marker).fill_null(False))
            .then(nw.lit("present"))
            .otherwise(nw.lit("empty"))
            .alias(coverage)
        ).drop(marker)
        return replace(
            result,
            _universe=universe
            if not {output, coverage}.intersection(
                universe.frame.collect_schema().names()
            )
            else None,
        )

    def explode_values(self, column: str, *, into: str, ordinal: str) -> Table:
        """Explode a scalar list while retaining parent and source positions.

        :param column: Validated scalar-list source column.
        :param into: Output scalar column.
        :param ordinal: Within-parent position column.
        :return: Native expanded table; empty/null lists emit no observations.
        """
        from ._native_tables import _explode_values_kernel, _pandas_meta

        meta = _pandas_meta(self.frame).drop(columns=[column])
        meta[into] = pd.Series(dtype=object)
        meta[ordinal] = pd.Series(dtype="int64")
        return self.map_partitions(
            _explode_values_kernel(column, into, ordinal), meta=meta
        )

    def ordered_values(
        self,
        *,
        keys: Sequence[str],
        column: str,
        into: str,
        max_group_rows: int = 5_000,
    ) -> Table:
        """Group bounded scalar evidence through native aggregation.

        :param keys: Identity grouping columns.
        :param column: Scalar evidence column.
        :param into: Sorted scalar-list output column.
        :param max_group_rows: Maximum evidence observations for one identity.
        :return: Grouped native table with bounded nested scalar presentation.
        """
        from ._native_tables import _ordered_values

        sizes = self.frame.group_by(*keys).agg(nw.len().alias("__group_rows"))
        invalid = sizes.filter(nw.col("__group_rows") > max_group_rows).select(
            nw.len().alias("invalid_count")
        )
        return replace(
            self,
            frame=_ordered_values(
                self.frame, tuple(keys), column, into, max_group_rows
            ),
            _checks=(
                *self._checks,
                _TableCheck(invalid, "Identity evidence group exceeds its bound"),
            ),
        )

    def sort(self, *keys: str, nulls_last: bool = True) -> Table:
        """Order the complete table using native global sorting.

        :param keys: Explicit deterministic ordering columns.
        :param nulls_last: Whether null ordering keys follow known values.
        :return: Ordered lazy table; partition-local sorting is insufficient.
        """
        return replace(self, frame=self.frame.sort(keys, nulls_last=nulls_last))

    def with_row_index(self, name: str) -> Table:
        """Assign globally correct ordinals without gathering dataframe rows.

        :param name: New integer ordering column.
        :return: Table using deferred partition-length prefix offsets.
        """
        from ._native_tables import _with_row_index

        return replace(self, frame=_with_row_index(self.frame, name))

    def fill_empty_lists(self, *columns: str) -> Table:
        """Represent unmatched nested groups as explicit empty lists.

        :param columns: Nullable list-of-records columns created by joins.
        :return: Table retaining requested-empty structural meaning.
        """
        from functools import partial

        from ._native_tables import _fill_lists, _pandas_meta

        return self.map_partitions(
            partial(_fill_lists, columns=columns), meta=_pandas_meta(self.frame)
        )

    def with_group_index(self, name: str, *, keys: Sequence[str]) -> Table:
        """Assign group ordinals globally through native cumulative counters.

        :param name: New integer ordinal column.
        :param keys: Nonempty grouping columns after explicit global sorting.
        :return: Table with zero-based ordinals that restart within each group.
        :raises CFBDTransformError: If grouping columns are unavailable.
        """
        from ._native_tables import _with_group_index

        if not keys or not set(keys) <= set(self.columns) or name in self.columns:
            raise CFBDTransformError(
                "Group indexing requires available keys and a new column"
            )
        return replace(
            self, frame=_with_group_index(self.frame, tuple(keys), name), _universe=None
        )

    def map_partitions(
        self, function: PartitionFunction, *, meta: pd.DataFrame
    ) -> Table:
        """Apply a bounded structural/domain kernel with explicit metadata.

        :param function: Pure kernel over one pandas partition.
        :param meta: Typed empty output frame; no sampling executes user code.
        :return: Table preserving inherited global checks.
        """
        from ._native_tables import _map_partitions

        return replace(
            self,
            frame=_map_partitions(self.frame, function, meta),
            _universe=None,
            _known_empty=False,
        )

    def normalize_text(self, column: str, *, into: str) -> Table:
        """Normalize whitespace and Unicode casefold with pandas string operations.

        :param column: Source text column.
        :param into: Explicit normalized-key column.
        :return: Native table with the normalized key; null remains null.
        """
        from ._native_tables import _normalization_kernel, _pandas_meta

        meta = _pandas_meta(self.frame)
        meta[into] = pd.Series(dtype="string")
        return replace(
            self.map_partitions(_normalization_kernel(column, into), meta=meta),
            _known_empty=self._known_empty,
        )

    def nested(
        self,
        column: str,
        *,
        fields: Mapping[str, str],
        dtypes: Mapping[str, str] | None = None,
    ) -> Table:
        """Project named fields from an object/struct column within partitions.

        :param column: Source validated struct column.
        :param fields: Child field names mapped to new output columns.
        :param dtypes: Explicit pandas nullable dtypes for projected columns.
        :return: Table preserving other columns and structural nulls.
        """
        from ._native_tables import _nested_kernel, _pandas_meta

        meta = _pandas_meta(self.frame)
        for target in fields.values():
            meta[target] = pd.Series(
                dtype=object if dtypes is None else dtypes.get(target, "object")
            )
        result = self.map_partitions(
            _nested_kernel(column, dict(fields), dict(dtypes or {})), meta=meta
        )
        return replace(
            result,
            _known_empty=self._known_empty,
            _universe=self._universe
            if self._universe is not None
            and not set(fields.values()).intersection(
                self._universe.frame.collect_schema().names()
            )
            else None,
        )

    def list_lengths(self, columns: Mapping[str, str]) -> Table:
        """Project list cardinalities through native partition string accessors.

        :param columns: Validated list columns mapped to integer size columns.
        :return: Table with nullable list sizes; empty lists have size zero.
        """
        from functools import partial

        from ._native_tables import _list_lengths, _pandas_meta

        meta = _pandas_meta(self.frame)
        for name in columns.values():
            meta[name] = pd.Series(dtype="Int64")
        return self.map_partitions(
            partial(_list_lengths, columns=dict(columns)), meta=meta
        )

    def pack(self, *, columns: Mapping[str, str], into: str) -> Table:
        """Pack explicit fields into source-faithful ordered struct records.

        :param columns: Source columns mapped to nested field names.
        :param into: Struct output column.
        :return: Table carrying other columns and an object/struct projection.
        """
        from ._native_tables import _pack_kernel, _pandas_meta

        if (
            not columns
            or not set(columns) <= set(self.columns)
            or len(set(columns.values())) != len(columns)
        ):
            raise CFBDTransformError("Packed fields are unavailable or collide")
        meta = _pandas_meta(self.frame)
        meta[into] = pd.Series(dtype=object)
        return self.map_partitions(_pack_kernel(dict(columns), into), meta=meta)

    def explode_records(
        self,
        column: str,
        *,
        fields: Mapping[str, str],
        ordinal: str,
        dtypes: Mapping[str, str] | None = None,
    ) -> Table:
        """Explode a validated record list with per-parent source ordinals.

        Empty and null lists emit no observations. This does not drop nulls in
        the fields of a real child observation.

        :param column: Source list-of-records column.
        :param fields: Nested field names mapped to new output columns.
        :param ordinal: Output child position within the original parent list.
        :param dtypes: Explicit nullable pandas dtypes for projected fields.
        :return: Expanded table with inherited checks and parent fields.
        """
        from ._native_tables import _explode_kernel, _pandas_meta

        meta = _pandas_meta(self.frame).drop(columns=[column])
        meta[ordinal] = pd.Series(dtype="int64")
        for target in fields.values():
            meta[target] = pd.Series(
                dtype=object if dtypes is None else dtypes.get(target, "object")
            )
        return self.map_partitions(
            _explode_kernel(column, dict(fields), ordinal, dict(dtypes or {})),
            meta=meta,
        )

    def ordered_records(
        self,
        *,
        keys: Sequence[str],
        column: str,
        into: str,
        ordinal_field: str,
        max_group_rows: int = 100_000,
        keep_ordinal: bool = False,
    ) -> Table:
        """Aggregate ordered nested records through native distributed grouping.

        :param keys: Group identity columns.
        :param column: Packed record column with a source ordinal field.
        :param into: Output list-of-records column.
        :param ordinal_field: Nested field retaining original source order.
        :param max_group_rows: Explicit maximum records in one nested group.
        :param keep_ordinal: Retain the ordinal as an analytical nested field.
        :return: Grouped table with bounded ordered record assembly.
        """
        from ._native_tables import _ordered_records

        sizes = self.frame.group_by(*keys).agg(nw.len().alias("__group_rows"))
        invalid = sizes.filter(nw.col("__group_rows") > max_group_rows).select(
            nw.len().alias("invalid_count")
        )
        return replace(
            self,
            frame=_ordered_records(
                self.frame,
                tuple(keys),
                column,
                into,
                ordinal_field,
                max_group_rows,
                keep_ordinal,
            ),
            _checks=(
                *self._checks,
                _TableCheck(invalid, "Nested group violates its record bound"),
            ),
        )

    def collect(self) -> pd.DataFrame:
        """Materialize this table explicitly through the local native scheduler.

        :return: Complete validated pandas frame; its size must fit caller memory.
        :raises CFBDTransformError: If a deferred global check fails.
        """
        from ._native_tables import _collect_table

        return _collect_table(self)


def concat_tables(tables: Iterable[Table]) -> Table:
    """Concatenate native tables without collecting their rows.

    :param tables: Non-empty finite sequence of compatible typed tables.
    :return: Concatenated graph carrying every inherited validation.
    :raises CFBDTransformError: If no table was supplied.
    """
    values = tuple(tables)
    if not values:
        raise CFBDTransformError("Table concatenation requires an input")
    return Table(
        nw.concat([table.frame for table in values]),
        _merge_checks(*(table._checks for table in values)),
    )


__all__ = ["Table", "concat_tables"]
