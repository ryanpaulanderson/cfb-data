# Ratings API

`client.ratings` implements CORE, team and conference SP+, SRS, expanded SRS,
Elo, and FPI. Nested SP+ and FPI components remain structured, nullable source
metrics remain nullable, and expanded SRS preserves division classification.

CORE, SP+, SRS, expanded SRS, and FPI require at least a year or team. The Elo
and conference SP+ routes retain the upstream optional filters.
