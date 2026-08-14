SELECT
    id,
    season,
    week,
    season_type,
    start_date,
    status,
    home_team_id,
    away_team_id,
    venue_id
FROM games
WHERE id = ?
