INSERT INTO plays
VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1)
ON CONFLICT(id) DO UPDATE SET
    game_id = excluded.game_id,
    drive_id = excluded.drive_id,
    play_type_id = excluded.play_type_id,
    play_type = excluded.play_type,
    last_seen_at = excluded.last_seen_at
