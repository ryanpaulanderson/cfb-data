# Metrics API

The Metrics namespace implements the eight documented PPA, win-probability,
and expected-points routes. Team and player PPA results preserve their nested
offense, defense, average, cumulative, and play-context splits. Player IDs are
accepted as positive integers in requests and remain strings in responses.

All methods return the selected eager DataFrame backend. pandas stores nested
splits as `object`; Polars uses native `Struct` columns. Required selector
combinations such as year-or-team and week-or-team fail before HTTP.
