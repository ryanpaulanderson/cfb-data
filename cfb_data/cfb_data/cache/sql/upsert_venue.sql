INSERT INTO venues
VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1)
ON CONFLICT(id) DO UPDATE SET
    name = excluded.name,
    normalized_name = excluded.normalized_name,
    city = excluded.city,
    state = excluded.state,
    last_seen_at = excluded.last_seen_at
