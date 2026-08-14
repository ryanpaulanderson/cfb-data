INSERT INTO team_aliases
VALUES (?, ?, ?)
ON CONFLICT(team_id, normalized_alias) DO UPDATE SET
    alias = excluded.alias
