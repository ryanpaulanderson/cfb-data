# Product constitution

`cfb-data` exists so analysts can use trustworthy college-football data without
becoming infrastructure engineers. This constitution governs product
decisions; [the repository engineering guide](https://github.com/ryanpaulanderson/cfb-data/blob/main/AGENTS.md)
governs how changes are engineered.

## I. Serve the analyst

A domain expert must be able to obtain a validated, analysis-ready result using
domain terms and safe defaults, without understanding transport, validation,
caching, or storage internals.

**Decision test:** Does every common capability have a minimal public example
and a black-box test through the default client?

## II. Be faithful before helpful

Preserve source meaning, structure, ordering, nulls, and uncertainty. Never
silently invent, impute, discard, or reinterpret data for convenience.

**Decision test:** Is every transformation or exclusion explicit, documented,
and tested, and is malformed source data prevented from becoming a public
result?

## III. Distinguish invalid from incomplete

Reject data that violates its contract, but represent valid empty, partial, or
unavailable data honestly. Never turn unknown into zero or missing into
success.

**Decision test:** Do tests cover malformed, empty, null, and partial responses,
exposing a reason when knowable and preserving unknown when it is not?

## IV. Reveal complexity progressively

The simple path and expert path must use the same validated execution engine.
Simplicity may hide mechanics; it may not weaken guarantees or change meaning.

**Decision test:** Do equivalent default and explicitly configured policies
produce equivalent logical results and enforce the same data contracts?

## V. Make consequential decisions explainable

When diagnostics are enabled, users must be able to understand where data came
from and what happened to retrieve, validate, cache, resolve, and materialize
it.

**Decision test:** Does a captured operation expose applicable source, redacted
request, cache disposition, freshness, attempt count, outcome, row count,
timing, and identity evidence without exposing secrets or payloads?

## VI. Configure policy, not correctness

If one behavior is correct, make it an invariant. If users face a legitimate
tradeoff, expose a typed, validated policy with a safe default.

**Decision test:** Does invalid configuration fail before external I/O, and is
every option's default and overridden behavior documented and tested?

## VII. Keep identity evidence-based and temporal

Canonical identities must enable cross-source analysis without erasing source
identities, historical validity, or resolution evidence. Ambiguity must remain
explicit.

**Decision test:** Is every resolved identity traceable to its source and
basis, and is an ambiguous fixture never silently assigned?

## VIII. Keep retrieval analysis-neutral

Endpoint results must remain source-shaped and backend-neutral. Opinionated
joins, features, and derived metrics belong in declared analytical layers with
explicit grain and semantics.

**Decision test:** Do pandas and Polars preserve the same logical values, nulls,
and ordering, and does every derived product declare its sources, row grain,
and metric definitions?

When clauses appear to conflict, preserve source fidelity and explicit
uncertainty first, then choose the easiest interface that keeps consequential
behavior observable and configurable. A decision may mark a clause not
applicable only when it explains why.
