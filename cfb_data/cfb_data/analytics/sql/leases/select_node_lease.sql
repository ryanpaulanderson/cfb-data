SELECT owner_token, run_id, node_id, acquired_at, expires_at
FROM node_execution_leases
WHERE lease_key = ?
