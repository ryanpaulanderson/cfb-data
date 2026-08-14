INSERT INTO vocabularies
VALUES (?, ?, ?, ?, ?, ?, 1, 1)
ON CONFLICT(namespace, id) DO UPDATE SET
    name = excluded.name,
    abbreviation = excluded.abbreviation,
    last_seen_at = excluded.last_seen_at
