INSERT INTO athlete_team_seasons
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(athlete_id, normalized_team_name, season) DO UPDATE SET
    team_name = excluded.team_name,
    last_seen_at = excluded.last_seen_at
