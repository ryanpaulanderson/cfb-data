UPDATE refresh_leases
SET expires_at = ?
WHERE key = ? AND owner_token = ?
