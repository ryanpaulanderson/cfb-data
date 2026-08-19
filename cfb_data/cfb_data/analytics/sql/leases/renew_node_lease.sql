UPDATE node_execution_leases
SET expires_at = ?
WHERE lease_key = ?
  AND owner_token = ?
  AND expires_at > ?
