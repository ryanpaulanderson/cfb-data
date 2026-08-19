WITH RECURSIVE ancestry(run_id, parent_run_id, depth) AS (
    SELECT run_id, parent_run_id, 0
    FROM runs WHERE run_id = ?
    UNION ALL
    SELECT parent.run_id, parent.parent_run_id, ancestry.depth + 1
    FROM runs AS parent
    JOIN ancestry ON parent.run_id = ancestry.parent_run_id
)
SELECT binding.*, object.manifest_json
FROM ancestry
JOIN runs AS run ON run.run_id = ancestry.run_id
JOIN node_artifact_bindings AS binding
  ON binding.run_id = ancestry.run_id
JOIN artifact_objects AS object
  ON object.content_digest = binding.content_digest
WHERE binding.node_fingerprint = ?
  AND binding.output_name = ?
  AND binding.checkpoint_eligible = 1
  AND run.credential_scope = ?
ORDER BY ancestry.depth, binding.binding_id DESC
LIMIT 1
