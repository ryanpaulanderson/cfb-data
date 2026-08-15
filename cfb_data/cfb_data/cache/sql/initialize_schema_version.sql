INSERT INTO cache_meta(key, value)
VALUES ('schema_version', ?)
ON CONFLICT(key) DO NOTHING
