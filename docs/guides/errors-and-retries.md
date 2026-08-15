# Errors and retries

All public library exceptions derive from {class}`cfb_data.CFBDError`. Error
messages and retry debug events contain safe endpoint, status, and attempt
metadata; they do not include API keys, query parameters, response payloads, or
other secrets.

## Exception taxonomy

| Exception | Meaning | Typical action |
| --- | --- | --- |
| {class}`cfb_data.CFBDConfigurationError` | API key, backend, base URL, timeout, or other client configuration is invalid | Correct configuration before opening the client |
| {class}`cfb_data.CFBDOptionalDependencyError` | A requested optional backend is not installed | Install `cfb-data[polars]` or `cfb-data[redis]`, or select an installed backend |
| {class}`cfb_data.CFBDCacheBackendError` | Strict cache or identity-catalog access could not be answered | Restore the configured backend or choose non-strict API access |
| {class}`cfb_data.CFBDCacheMissError` | Local-only response access has no retained validated record | Hydrate or fetch while network access is permitted |
| {class}`cfb_data.CFBDIdentityNotFoundError` | Exact identity resolution found no candidate | Correct the identifier/name or hydrate the relevant partition |
| {class}`cfb_data.CFBDIdentityAmbiguityError` | Multiple identities matched the same exact normalized value | Add team, season, or another supported scope |
| {class}`cfb_data.CFBDClientStateError` | The one-shot async lifecycle was violated | Create and enter a fresh client |
| {class}`cfb_data.CFBDRequestValidationError` | Keyword filters violate the endpoint request model | Correct field names, values, or selector combinations |
| {class}`cfb_data.CFBDTimeoutError` | A finite request attempt timed out | Retry according to application policy or investigate service/network health |
| {class}`cfb_data.CFBDTLSError` | TLS negotiation or certificate validation failed | Investigate trust or interception; do not disable TLS verification |
| {class}`cfb_data.CFBDTransportError` | Another connection or payload transport failure occurred | Treat as an operational failure after built-in retries |
| {class}`cfb_data.CFBDAuthenticationError` | The API rejected authentication | Check the API key |
| {class}`cfb_data.CFBDAuthorizationError` | The account lacks access to the endpoint | Check the endpoint's required tier |
| {class}`cfb_data.CFBDRateLimitError` | The API rate limit was exhausted | Back off; inspect `retry_after_seconds` when present |
| {class}`cfb_data.CFBDServerError` | The API returned a server error after retries | Retry later or investigate upstream status |
| {class}`cfb_data.CFBDHTTPError` | Another unsuccessful HTTP response occurred | Inspect the safe `status` and endpoint metadata |
| {class}`cfb_data.CFBDResponseDecodeError` | The body was not complete valid JSON | Treat as an upstream or transport failure |
| {class}`cfb_data.CFBDResponseValidationError` | Decoded JSON violated the declared response contract | Treat as an upstream contract change or malformed response |
| {class}`cfb_data.CFBDDataFrameConversionError` | Validated rows could not be represented without violating the frame contract | Report the endpoint and selected backend |

## Default retry policy

The immutable {class}`cfb_data.RetryPolicy` makes at most three total attempts
for safe GET requests. It retries connection failures, timeouts, truncated
payloads, and HTTP `408`, `429`, `500`, `502`, `503`, and `504` with capped
exponential full-jitter backoff.

Valid numeric and HTTP-date `Retry-After` values are honored up to 90 seconds.
A longer server-requested delay fails immediately and remains available as
`retry_after_seconds` on the resulting HTTP error. Redirects are disabled,
TLS verification remains enabled, every attempt has a finite timeout, and
async cancellation is preserved.

Customize the bounded policy at client construction:

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

Set `RetryPolicy(max_attempts=1)` to disable retries. `max_attempts` includes
the initial request.
