SELECT state FROM artifact_gc_transitions
WHERE content_digest = ?
ORDER BY transition_id DESC
LIMIT 1
