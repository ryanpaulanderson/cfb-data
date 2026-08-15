INSERT INTO games
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1)
ON CONFLICT(id) DO UPDATE SET
    season = excluded.season,
    week = excluded.week,
    season_type = excluded.season_type,
    start_date = excluded.start_date,
    status = excluded.status,
    home_team_id = excluded.home_team_id,
    away_team_id = excluded.away_team_id,
    venue_id = excluded.venue_id,
    last_seen_at = excluded.last_seen_at
