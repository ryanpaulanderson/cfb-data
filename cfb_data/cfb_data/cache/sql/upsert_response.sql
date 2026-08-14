INSERT INTO response_records
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(key) DO UPDATE SET
    endpoint = excluded.endpoint,
    response_contract = excluded.response_contract,
    body = excluded.body,
    fetched_at = excluded.fetched_at,
    fresh_until = excluded.fresh_until,
    retained_until = excluded.retained_until,
    etag = excluded.etag,
    last_modified = excluded.last_modified,
    row_count = excluded.row_count
