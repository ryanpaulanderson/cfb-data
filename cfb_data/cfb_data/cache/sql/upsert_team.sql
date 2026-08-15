INSERT INTO teams
VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)
ON CONFLICT(id) DO UPDATE SET
    school = excluded.school,
    normalized_school = excluded.normalized_school,
    abbreviation = excluded.abbreviation,
    normalized_abbreviation = excluded.normalized_abbreviation,
    alternate_names_json = excluded.alternate_names_json,
    last_seen_at = excluded.last_seen_at
