SELECT state FROM artifact_pin_transitions
WHERE content_digest = ? AND pin_name = ?
ORDER BY transition_id DESC
LIMIT 1
