INSERT INTO conference_affiliations
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(team_id, conference_id, start_year) DO UPDATE SET
    end_year = excluded.end_year,
    last_seen_at = excluded.last_seen_at
