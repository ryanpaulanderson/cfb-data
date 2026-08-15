# Advanced errors and retries

This page is the complete exception and retry reference. For common fixes,
start with [Troubleshooting requests](../guides/errors-and-retries.md).

## Exception reference

All public library exceptions derive from {class}`cfb_data.CFBDError`.

| Exception | Meaning | Typical action |
| --- | --- | --- |
| {class}`cfb_data.CFBDConfigurationError` | API key, backend, base URL, timeout, or another client option is invalid | Correct client configuration |
| {class}`cfb_data.CFBDOptionalDependencyError` | A requested optional backend is not installed | Install `cfb-data[polars]` or `cfb-data[redis]` |
| {class}`cfb_data.CFBDCacheBackendError` | Strict cache or identity access could not be answered | Restore the backend or use ordinary API access |
| {class}`cfb_data.CFBDCacheMissError` | `local_only` has no retained response | Fetch once while network access is available |
| {class}`cfb_data.CFBDIdentityNotFoundError` | Exact identity resolution found no candidate | Correct the value or hydrate related data |
| {class}`cfb_data.CFBDIdentityAmbiguityError` | Several identities matched the normalized value | Add team, season, or another scope |
| {class}`cfb_data.CFBDClientStateError` | The one-shot async lifecycle was violated | Create and enter a fresh client |
| {class}`cfb_data.CFBDRequestValidationError` | Keyword filters violate the request model | Correct names, values, or selector combinations |
| {class}`cfb_data.CFBDTimeoutError` | A request attempt timed out | Retry later or inspect connection health |
| {class}`cfb_data.CFBDTLSError` | TLS negotiation or certificate validation failed | Inspect certificate trust or interception |
| {class}`cfb_data.CFBDTransportError` | Another connection or payload failure occurred | Retry later or inspect the connection |
| {class}`cfb_data.CFBDAuthenticationError` | The API rejected authentication | Check the API key |
| {class}`cfb_data.CFBDAuthorizationError` | The account lacks endpoint access | Check the endpoint's required tier |
| {class}`cfb_data.CFBDRateLimitError` | The API rate limit was exhausted | Back off and inspect `retry_after_seconds` |
| {class}`cfb_data.CFBDServerError` | The API returned a server error after retries | Retry later |
| {class}`cfb_data.CFBDHTTPError` | Another unsuccessful HTTP response occurred | Inspect `status` and endpoint metadata |
| {class}`cfb_data.CFBDResponseDecodeError` | The body was not complete valid JSON | Treat as an upstream or connection failure |
| {class}`cfb_data.CFBDResponseValidationError` | JSON did not match the response model | Check for an upstream API change |
| {class}`cfb_data.CFBDDataFrameConversionError` | Validated rows could not become the selected frame | Report endpoint and backend |

## Default retry behavior

{class}`cfb_data.RetryPolicy` makes at most three total attempts for safe GET
requests. It retries connection failures, timeouts, truncated payloads, and
HTTP `408`, `429`, `500`, `502`, `503`, and `504`.

Backoff uses capped exponential full jitter. Valid numeric and HTTP-date
`Retry-After` values are honored up to 90 seconds. A longer requested delay
fails immediately and remains available as `retry_after_seconds` on the error.

Redirects are disabled. TLS verification remains enabled, each attempt has a
finite timeout, and async cancellation is preserved.

## Customize retries

```python
from cfb_data import CFBDClient, RetryPolicy

policy = RetryPolicy(
    max_attempts=4,
    base_delay_seconds=0.25,
    max_backoff_seconds=4.0,
    max_retry_after_seconds=20.0,
)

async with CFBDClient(retry_policy=policy) as client:
    scoreboard = await client.games.scoreboard()
```

`max_attempts` includes the initial request. Set it to `1` to disable retries.

Error messages and retry debug events include endpoint, status, and attempt
metadata without API keys, query values, response payloads, or Redis
credentials.
