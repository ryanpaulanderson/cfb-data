SELECT binding.*, object.manifest_json
FROM node_artifact_bindings AS binding
JOIN runs AS run ON run.run_id = binding.run_id
JOIN artifact_objects AS object
  ON object.content_digest = binding.content_digest
WHERE binding.node_fingerprint = ?
  AND binding.output_name = ?
  AND binding.checkpoint_eligible = 1
  AND run.credential_scope = ?
ORDER BY binding.binding_id DESC
LIMIT 1
