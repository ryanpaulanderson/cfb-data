SELECT DISTINCT binding.run_id
FROM node_artifact_bindings AS binding
WHERE binding.content_digest = ?
ORDER BY binding.run_id
