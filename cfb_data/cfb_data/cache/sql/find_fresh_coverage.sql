SELECT capabilities_json, projection_contract
FROM coverage
WHERE endpoint = ?
  AND canonical_filters = ?
  AND status = 'complete'
  AND fresh_until > ?
