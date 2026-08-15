INSERT INTO athletes
VALUES (?, ?, ?, ?, ?, ?, 1, 1)
ON CONFLICT(id) DO UPDATE SET
    name = excluded.name,
    normalized_name = excluded.normalized_name,
    position = excluded.position,
    last_seen_at = excluded.last_seen_at
