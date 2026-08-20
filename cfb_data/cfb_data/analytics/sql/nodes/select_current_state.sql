SELECT state FROM node_transitions
WHERE run_id = ? AND node_id = ?
ORDER BY transition_id DESC
LIMIT 1
