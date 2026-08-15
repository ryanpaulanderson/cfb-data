INSERT INTO refresh_leases(key, owner_token, acquired_at, expires_at)
VALUES (?, ?, ?, ?)
ON CONFLICT(key) DO UPDATE SET
    owner_token = excluded.owner_token,
    acquired_at = excluded.acquired_at,
    expires_at = excluded.expires_at
WHERE refresh_leases.expires_at <= ?
