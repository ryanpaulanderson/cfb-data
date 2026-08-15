INSERT INTO coverage_failures
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(partition_key) DO UPDATE SET
    failure_category = excluded.failure_category,
    failed_at = excluded.failed_at
