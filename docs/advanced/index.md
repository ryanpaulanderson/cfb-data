# Advanced details

The main guides focus on common analysis tasks. This section keeps the exact
behavior available when you need to tune a cache, depend on a dtype, handle a
specific exception, or understand every accepted value.

| Topic | What is covered |
| --- | --- |
| [Request details](request-details.md) | Complete enum values, recurring validation rules, and field aliases |
| [Result details](result-details.md) | pandas and Polars dtypes, Arrow representation, nested values, and Parquet internals |
| [Cache behavior](cache-behavior.md) | TTLs, stale responses, remote Redis, identity matching, hydration, and cleanup |
| [Errors and retries](errors-and-retries.md) | Full exception reference, retryable statuses, delay limits, and policy settings |

These pages are still written as user documentation. For design rationale and
implementation boundaries, start with the [request lifecycle
architecture](../architecture/request-lifecycle.md) and its linked decision
records.
