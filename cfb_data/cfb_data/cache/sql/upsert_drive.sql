INSERT INTO drives
VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)
ON CONFLICT(id) DO UPDATE SET
    game_id = excluded.game_id,
    offense_team_id = excluded.offense_team_id,
    offense_team = excluded.offense_team,
    defense_team_id = excluded.defense_team_id,
    defense_team = excluded.defense_team,
    last_seen_at = excluded.last_seen_at
