# Coaches API

`client.coaches` exposes the historical summary, canonical profile, detailed
season, and continuous tenure routes. Python request names such as `coach_id`,
`first_name`, `min_year`, and `max_year` serialize to the upstream aliases.

The profile route returns one row. Historical seasons, records, team context,
recruiting, poll résumé, scoring, CFP, draft, and tenure data remain nested
according to their endpoint grain. Timestamp fields must be timezone-aware and
are normalized to UTC; upstream date-only fields remain ISO date strings.
