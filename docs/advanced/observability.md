# Retrieval observability

Pass a `RetrievalStats` collector when you need exact visibility into what one
or more clients did:

```python
from cfb_data import CFBDClient, RetrievalStats, SQLiteCacheConfig

stats = RetrievalStats()

async with CFBDClient(
    cache=SQLiteCacheConfig(),
    observer=stats,
) as client:
    await client.games.list(year=2025)
    await client.games.list(year=2025)

snapshot = stats.snapshot()
print(snapshot.endpoint_retrievals)
print(snapshot.http_attempts)
print(snapshot.fresh_cache_hits)
print(snapshot.fresh_hit_rate)
print(snapshot.by_endpoint["/games"])
```

The collector can be read during or after the client context. `snapshot()` is
immutable, and `reset()` starts a new measurement interval. The collector keeps
only counters and active operation identifiers; it does not retain event,
request, response, or cache bodies.

## Count definitions

- `endpoint_retrievals` counts serialized, validated endpoint requests that
  reach the shared executor. A request rejected by its request model never
  reaches cache or transport and is not counted.
- `http_attempts` counts each client-side attempt started by the HTTP transport.
  Retries and conditional `304 Not Modified` requests each count because they
  contact the API. A failed connection attempt may not have reached the provider.
- `retries` counts attempts numbered two or higher.
- `fresh_cache_hits` counts conclusive initial lookups that returned a fresh,
  validated record.
- `retained_cache_serves` counts stale records explicitly returned by
  `local_only` mode. `stale_fallbacks` counts retained records returned after an
  allowed exhausted transport failure.
- `cache_backend_failures` is separate from `cache_misses`. A backend that could
  not answer did not prove that a record was absent.
- `coalesced_retrievals` counts process-local followers. A follower can complete
  successfully without adding another HTTP attempt, while its retrieval source
  remains the network or cache source used by the shared leader.
- `lease_waits` and `lease_timeouts` describe distributed refresh coordination.
  A waiter that reads the completed refresh from Redis is cache-served, not a
  process-local coalesced retrieval.
- `response_bytes` and `cache_bytes_written` contain bounded byte counts, never
  payloads.

`fresh_hit_rate` is fresh hits divided by conclusive initial cache lookups. It
excludes disabled caching, explicit bypass, operational endpoints, and backend
failures. `cache_served_rate` is successful retrievals ultimately served from a
fresh, conditionally revalidated, retained, or stale-fallback record divided by
all successful retrievals. A conditional revalidation counts as cache-served
because its returned body comes from the retained record, while its `304`
request still counts as an HTTP attempt. `network_free_rate` is successful
retrievals that initiated no HTTP attempt divided by all successful retrievals.

## Shared Redis and several processes

`RetrievalStats` observes only clients to which that Python object was passed.
When several processes share Redis, the process that performs a refresh sees
the HTTP attempt and a follower process sees its lease wait. Send events to an
application-owned shared metrics system when you need a cross-process total;
cfb-data does not write monitoring counters into the response cache.

## Custom observers

Implement the callable `RetrievalObserver` protocol to integrate with another
system:

```python
from cfb_data import RetrievalEvent


def observe(event: RetrievalEvent) -> None:
    event_queue.put_nowait(event)


async with CFBDClient(observer=observe) as client:
    await client.games.calendar(year=2025)
```

Observers are synchronous and run in emission order. Keep them non-blocking;
enqueue into a bounded application-owned queue before performing I/O. If an
observer raises, cfb-data logs one bounded warning, disables it, and preserves
the retrieval result.

Events contain fixed endpoint paths, parameter names without values, stable
outcome categories, counts, sizes, durations, and random correlation IDs. They
never contain credentials, query values, full URLs, cache keys, validators,
response or cache bodies, exception objects, or exception messages.
