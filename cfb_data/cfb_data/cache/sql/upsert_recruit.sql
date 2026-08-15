INSERT INTO recruits
VALUES (?, ?, ?, ?, ?, ?, 1, 1)
ON CONFLICT(id) DO UPDATE SET
    athlete_id = excluded.athlete_id,
    name = excluded.name,
    year = excluded.year,
    last_seen_at = excluded.last_seen_at
