DELETE FROM node_execution_leases
WHERE lease_key = ?
  AND owner_token = ?
