# Venues API

`client.venues.list()` calls `GET /venues` without filters and returns one row
per venue. `Venue` owns the shared location contract reused by nested Team
locations.

Columns preserve the upstream identity, name, address, timezone, coordinates,
elevation, capacity, construction year, playing surface, and dome fields.
Nullable values remain nullable in both supported frame backends.
