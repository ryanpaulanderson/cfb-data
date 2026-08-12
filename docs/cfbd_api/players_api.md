# Players API

`client.players` implements search, usage, season overview, returning
production, and transfer portal data. The upstream season overview is validated
as one nested object and returned as a one-row frame. Transfer timestamps must
be timezone-aware and are normalized to UTC.

The upstream controller's deliberately hidden `/player/ppa/passing` route is
not exposed. Player search preserves team-stint history and response IDs as
strings; request filters use positive integer `player_id` values consistently
with the rest of the client.
