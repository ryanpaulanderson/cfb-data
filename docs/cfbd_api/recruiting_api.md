# Recruiting API

`client.recruiting` exposes player rankings, team class rankings, and team
position-group aggregates. Player requests require a year or committed team;
group requests validate ascending optional `start_year` and `end_year` values.

Recruit hometown details remain nested. Numeric database aggregates returned
by the API as strings are validated and normalized to the declared integer or
float columns before DataFrame conversion.
