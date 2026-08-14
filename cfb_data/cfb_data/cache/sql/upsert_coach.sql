INSERT INTO coaches
VALUES (?, ?, ?, ?, ?, ?, 1, 1)
ON CONFLICT(id) DO UPDATE SET
    name = excluded.name,
    normalized_name = excluded.normalized_name,
    wikidata_id = excluded.wikidata_id,
    last_seen_at = excluded.last_seen_at
