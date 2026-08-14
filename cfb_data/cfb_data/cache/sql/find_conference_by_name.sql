SELECT id, name, abbreviation, classification
FROM conferences
WHERE normalized_name = ? OR normalized_abbreviation = ?
