INSERT INTO runs (
    run_id, recipe_id, recipe_revision, recipe_kind,
    parameter_fingerprint, graph_fingerprint, parent_run_id,
    credential_scope, max_http_attempts, source_behavior, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
