SELECT DISTINCT a.id, a.name, a.position, m.team_name, m.season
FROM athletes AS a
LEFT JOIN athlete_team_seasons AS m ON m.athlete_id = a.id
WHERE a.normalized_name = ?
  AND (? IS NULL OR m.normalized_team_name = ?)
  AND (? IS NULL OR m.season = ?)
ORDER BY a.id, m.season
