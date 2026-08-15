INSERT INTO coach_team_seasons
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(coach_id, team_id, start_year) DO UPDATE SET
    end_year = excluded.end_year,
    tenure_id = excluded.tenure_id,
    last_seen_at = excluded.last_seen_at
