INSERT INTO node_artifact_bindings (
    run_id, node_id, output_name, node_fingerprint,
    content_digest, placement, committed_at
) VALUES (?, ?, ?, ?, ?, ?, ?)
