# Info API

The Info namespace exposes operational account metadata rather than analytical
tables, so both methods return validated Pydantic models independent of the
selected DataFrame backend.

| Method | Route | Filters | Result |
| --- | --- | --- | --- |
| `client.info.account` | `GET /info` | none | `UserInfo` |
| `client.info.usage` | `GET /info/usage` | `days`, `limit`, `api` | `UserUsage` |

`days` accepts integers from 1 through 31, `limit` accepts integers from 1
through 50, and `api` accepts `all`, `cfb`, or `cbb`. The usage response
preserves window, totals, endpoint, and recent-request metadata as nested
models.

```python
async with CFBDClient() as client:
    account = await client.info.account()
    usage = await client.info.usage(days=7, limit=25, api="cfb")

print(account.tier_name)
print(usage.totals)
```
