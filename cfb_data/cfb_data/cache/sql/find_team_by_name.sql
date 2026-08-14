SELECT DISTINCT t.id, t.school, t.abbreviation, t.alternate_names_json
FROM teams AS t
LEFT JOIN team_aliases AS a ON a.team_id = t.id
WHERE t.normalized_school = ?
   OR t.normalized_abbreviation = ?
   OR a.normalized_alias = ?
