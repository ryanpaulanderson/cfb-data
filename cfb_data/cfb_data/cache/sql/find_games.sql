SELECT
    g.id,
    g.season,
    g.week,
    g.season_type,
    g.start_date,
    g.status,
    g.home_team_id,
    g.away_team_id,
    g.venue_id
FROM games AS g
WHERE g.season = ?
  AND (? IS NULL OR g.week = ?)
  AND (
      ? IS NULL
      OR EXISTS (
          SELECT 1
          FROM teams AS t
          LEFT JOIN team_aliases AS a ON a.team_id = t.id
          WHERE (t.id = g.home_team_id OR t.id = g.away_team_id)
            AND (
                t.normalized_school = ?
                OR t.normalized_abbreviation = ?
                OR a.normalized_alias = ?
            )
      )
  )
ORDER BY g.start_date, g.id
