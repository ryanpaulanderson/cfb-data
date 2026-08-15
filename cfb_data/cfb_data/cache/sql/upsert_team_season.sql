INSERT INTO team_seasons
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(team_id, season) DO UPDATE SET
    conference_name = excluded.conference_name,
    venue_id = excluded.venue_id,
    last_seen_at = excluded.last_seen_at
