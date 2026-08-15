SELECT
    key,
    endpoint,
    response_contract,
    body,
    fetched_at,
    fresh_until,
    retained_until,
    etag,
    last_modified,
    row_count
FROM response_records
WHERE key = ?
