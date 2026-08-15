INSERT INTO catalog_observations
VALUES (?, ?, ?)
ON CONFLICT(namespace, grain) DO UPDATE SET
    payload = excluded.payload
