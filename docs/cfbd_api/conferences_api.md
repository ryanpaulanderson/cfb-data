# Conferences API

| Method | Route | Filters |
| --- | --- | --- |
| `client.conferences.list` | `GET /conferences` | `year`, `classification` |
| `client.conferences.changes` | `GET /conferences/changes` | required `year` |
| `client.conferences.affiliations` | `GET /conferences/affiliations` | `team`, `conference`, `year`, `min_year`, `max_year`, `classification` |

`year` cannot be combined with an affiliation year range, and `min_year`
cannot exceed `max_year`. `ConferenceClassification` includes the official
`fbs`, `fcs`, `ii`, `ii/iii`, and `iii` values.

All three methods return the selected DataFrame backend while preserving
upstream row order and exact model field order.
