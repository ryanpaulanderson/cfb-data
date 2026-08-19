SELECT state FROM run_retention_transitions
WHERE run_id = ?
ORDER BY transition_id DESC
LIMIT 1
