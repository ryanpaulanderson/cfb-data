SELECT object.content_digest, object.manifest_json
FROM artifact_objects AS object
WHERE NOT EXISTS (
    SELECT 1
    FROM node_artifact_bindings AS binding
    JOIN run_retention_transitions AS retention
      ON retention.run_id = binding.run_id
     AND retention.transition_id = (
        SELECT MAX(latest.transition_id)
        FROM run_retention_transitions AS latest
        WHERE latest.run_id = binding.run_id
     )
    WHERE binding.content_digest = object.content_digest
      AND retention.state = 'active'
)
  AND NOT EXISTS (
    SELECT 1 FROM artifact_pin_transitions AS pin
    WHERE pin.content_digest = object.content_digest
      AND pin.transition_id = (
        SELECT MAX(latest.transition_id)
        FROM artifact_pin_transitions AS latest
        WHERE latest.content_digest = object.content_digest
          AND latest.pin_name = pin.pin_name
      )
      AND pin.state = 'pinned'
  )
  AND NOT EXISTS (
    SELECT 1 FROM artifact_gc_transitions AS gc
    WHERE gc.content_digest = object.content_digest
      AND gc.transition_id = (
        SELECT MAX(latest.transition_id)
        FROM artifact_gc_transitions AS latest
        WHERE latest.content_digest = object.content_digest
      )
      AND gc.state IN ('deleting', 'deleted')
  )
ORDER BY object.content_digest
