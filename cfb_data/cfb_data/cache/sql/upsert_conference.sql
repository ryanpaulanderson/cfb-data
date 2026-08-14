INSERT INTO conferences
VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)
ON CONFLICT(id) DO UPDATE SET
    name = excluded.name,
    normalized_name = excluded.normalized_name,
    abbreviation = excluded.abbreviation,
    normalized_abbreviation = excluded.normalized_abbreviation,
    classification = excluded.classification,
    last_seen_at = excluded.last_seen_at
