# Notices of decision

Notices of decision (NODs) record consequential project choices in the context
in which they were made. They explain the question presented, the constraints
and evidence considered, the alternatives evaluated, the reasoning that led to
the outcome, and the follow-up implications.

NODs complement architecture decision records rather than replace them:

- a NOD explains **how and why** the project reached a decision;
- an ADR defines the resulting **technical architecture and contract**;
- current user-facing behavior remains documented in the project README and
  project-status documents.

NODs use a four-digit sequence and a descriptive filename. Their status is one
of `Proposed`, `Decided`, or `Superseded`. A later decision that materially
changes an earlier outcome should add a new NOD and link both records instead
of rewriting the original reasoning.

## Decision index

- [`0001-canonical-nested-tabular-representation.md`](0001-canonical-nested-tabular-representation.md)
  — choose Arrow and versioned Parquet as the backend-neutral contract for
  nested tabular responses.
