INSERT INTO node_execution_leases (
    lease_key, owner_token, run_id, node_id, acquired_at, expires_at
) VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(lease_key) DO UPDATE SET
    owner_token = excluded.owner_token,
    run_id = excluded.run_id,
    node_id = excluded.node_id,
    acquired_at = excluded.acquired_at,
    expires_at = excluded.expires_at
WHERE node_execution_leases.expires_at <= ?
