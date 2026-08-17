# ADR 0005: Expose typed client retrieval observability

- Status: Accepted
- Date: 2026-08-16
- Applies from: Public retrieval-observer implementation

## Context

The response cache already distinguishes fresh hits, retained stale records,
misses, corruption, refresh coordination, backend failures, and stale fallback.
The transport separately owns every real HTTP attempt and retry. Debug logs make
some of these decisions visible to a human, but they are not a stable public
contract and require applications to parse strings to calculate API attempts or
cache performance.

Returning diagnostics with every endpoint result would change the established
DataFrame and Pydantic return contracts. Storing counters in SQLite or Redis
would couple observation to persistence, add I/O to the retrieval path, and
still fail to describe cache-disabled requests consistently. Binding directly
to a logging, metrics, or tracing framework would add policy and dependencies
that applications already own.

## Decision

`CFBDClient` accepts an optional synchronous `RetrievalObserver`. The observer
receives immutable, bounded events from the existing executor, cache
coordinator, and HTTP transport boundaries. No observer is configured by
default.

The public package includes `RetrievalStats`, a bounded in-memory observer that
keeps aggregate and per-endpoint counters and returns immutable snapshots. It
does not retain raw events, requests, responses, cache records, or exceptions.
Applications that need another metrics or tracing system can implement the same
small observer protocol without changing domain resources.

One validated endpoint execution has an operation identifier. One refresh that
may be shared by process-local or distributed followers has a separate refresh
identifier. HTTP attempts belong to the refresh that actually performs them;
followers do not duplicate the count.

`http_attempts` counts client-side attempts started by the transport. Retries
and conditional requests count separately. This is exact client behavior, but a
connection failure cannot prove that the provider received or billed a request.

Observers are process-local. Reusing one `RetrievalStats` instance can aggregate
several clients in a process. Cross-process totals require forwarding events to
an application-owned shared metrics system; the response cache does not become
a metrics database.

## Failure and lifecycle policy

Observers run synchronously so event order is deterministic and the library
does not own background tasks or observer resources. A custom observer must
return promptly; an integration that performs I/O should enqueue into its own
bounded queue.

If an observer raises an ordinary exception or raises `CancelledError` from the
synchronous callback, the client logs one bounded warning, disables that
observer, and continues retrieval. The warning contains event and exception
categories only. Cancellation raised by cache or transport work remains
preserved and receives terminal attempt and retrieval events before it is
re-raised.

## Security contract

Events may contain fixed endpoint paths, query-field names without values,
cache modes and profiles, stable outcome and source categories, attempt
numbers, HTTP status classes, row counts, bounded byte counts, finite
durations, and random correlation identifiers. A successful conditional `304`
attempt is attributed to a revalidated-cache source because the returned body
comes from the retained record.

Events never contain API keys, authorization headers, query values, full URLs,
credential-scope digests, cache keys, validators, Redis locations, response or
cache bodies, exception objects, or exception messages. Safe failure categories
are copied into bounded strings so observer retention cannot retain an unsafe
exception chain.

## Consequences

- A notebook can report cache hit rates and observed HTTP attempts with one
  optional collector.
- Applications can adapt the same events to their logging, metrics, or tracing
  framework without a cfb-data runtime dependency on that framework.
- SQLite and Redis retain one observability contract because decisions are
  emitted by their shared coordinator rather than backend implementations.
- Instrumentation remains opt-in and does not change endpoint return types,
  validation, cache policy, retries, cancellation, or resource ownership.
- Retrieval observation ends after response validation. DataFrame presentation
  and identity-resolution evidence can add separate event families if a future
  requirement needs full analytical-operation tracing.

## Alternatives considered

### Keep debug logging as the only surface

Rejected. Log text is useful for troubleshooting but is not a typed contract,
cannot safely drive exact counters, and couples applications to message format.

### Return result and metadata tuples

Rejected. This would change every public endpoint result and make ordinary
analysis more complex even when diagnostics are not needed.

### Store global counters in the cache backend

Rejected. It adds write load, conflates cache ownership with metrics retention,
does not cover cache-disabled clients naturally, and cannot provide application
specific aggregation policy.

### Depend directly on OpenTelemetry or a metrics client

Rejected. A small typed observer supports those adapters without imposing a
framework, exporter lifecycle, or new runtime dependency on every user.
