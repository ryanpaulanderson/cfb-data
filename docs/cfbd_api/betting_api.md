# Betting API

`client.betting.lines` implements historical betting lines. Requests require a
season year or `game_id` and can filter by season type, week, participating or
home/away team, conference, and provider.

One frame row represents a game. Its `lines` column preserves the provider
collection, including open/current spreads and totals plus home and away money
lines. Game timestamps must be timezone-aware and are normalized to UTC.
