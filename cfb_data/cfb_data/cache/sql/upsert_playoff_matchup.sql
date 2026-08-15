INSERT INTO playoff_matchups
VALUES (?, ?, ?, ?, ?, 1, 1)
ON CONFLICT(id) DO UPDATE SET
    season = excluded.season,
    linked_game_id = excluded.linked_game_id,
    last_seen_at = excluded.last_seen_at
