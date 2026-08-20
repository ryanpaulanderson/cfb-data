SELECT 1
FROM node_artifact_bindings AS binding
WHERE binding.run_id = ?
  AND EXISTS (
    SELECT 1 FROM artifact_gc_transitions AS gc
    WHERE gc.content_digest = binding.content_digest
      AND gc.transition_id = (
        SELECT MAX(latest.transition_id)
        FROM artifact_gc_transitions AS latest
        WHERE latest.content_digest = binding.content_digest
      )
      AND gc.state IN ('deleting', 'deleted')
  )
LIMIT 1
