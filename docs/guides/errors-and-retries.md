# Troubleshooting requests

Most problems fall into a few recognizable groups: configuration, invalid
filters, access limits, temporary network failures, or an unexpected change in
the upstream data.

## Start with the exception name

All library exceptions inherit from {class}`cfb_data.CFBDError`, so you can
catch one base class while exploring:

```python
from cfb_data import CFBDError, CFBDClient

try:
    async with CFBDClient() as client:
        games = await client.games.list(year=2024)
except CFBDError as exc:
    print(type(exc).__name__, exc)
```

Once your script needs different recovery behavior, catch the narrower
exception.

## Common problems

| Exception or symptom | Likely cause | What to try |
| --- | --- | --- |
| `CFBDConfigurationError` | Missing API key or invalid client option | Check `CFBD_API_KEY` and client construction. |
| `CFBDRequestValidationError` | Misspelled filter, unsupported value, or missing selector | Compare the call with the endpoint reference. |
| `CFBDAuthenticationError` | The API key was rejected | Check that the key is current and copied without extra whitespace. |
| `CFBDAuthorizationError` | The endpoint requires a different Patreon tier | Check the access note in the endpoint reference. |
| `CFBDRateLimitError` | The account has exhausted its available calls | Wait before retrying and consider SQLite or Redis caching. |
| `CFBDTimeoutError` or `CFBDTransportError` | Temporary API or connection problem | Try again later; the client has already attempted its normal retries. |
| `CFBDResponseValidationError` | The API returned a shape the installed package did not expect | Check for a newer package version or report the endpoint and error. |
| `CFBDDataFrameConversionError` | Validated data could not be represented in the selected backend | Report the endpoint, backend, and package version. |

## Handle the errors you can act on

This example distinguishes a bad local request from API access and rate-limit
problems:

```python
from cfb_data import (
    CFBDAuthenticationError,
    CFBDAuthorizationError,
    CFBDClient,
    CFBDRateLimitError,
    CFBDRequestValidationError,
)

try:
    async with CFBDClient() as client:
        games = await client.games.list(year=2024)
except CFBDRequestValidationError as exc:
    print(f"Fix the filters: {exc}")
except CFBDAuthenticationError:
    print("Check CFBD_API_KEY.")
except CFBDAuthorizationError:
    print("This endpoint may require another access tier.")
except CFBDRateLimitError as exc:
    print(f"Rate limited after {exc.attempts} attempts.")
```

## The client already retries temporary failures

By default, a request gets up to three total attempts for common temporary
connection, timeout, rate-limit, and server failures. Most scripts do not need
to configure this.

If you want only one attempt—for example, in an interactive notebook where you
prefer immediate feedback—set:

```python
from cfb_data import CFBDClient, RetryPolicy

async with CFBDClient(retry_policy=RetryPolicy(max_attempts=1)) as client:
    games = await client.games.list(year=2024)
```

## When reporting a problem

The most useful details are:

- the endpoint method, such as `client.games.list`;
- the exception class and message;
- the `cfb-data` version;
- whether pandas or Polars was selected; and
- a minimal call with secrets and personal paths removed.

Library error messages omit API keys, query values, and response payloads, but
it is still worth checking copied logs before sharing them.

## Go deeper

[Advanced errors and retries](../advanced/errors-and-retries.md) lists every
exception class, retryable status, delay limit, and retry-policy option.
