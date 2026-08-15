INSERT INTO coverage
VALUES (
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
    '5.24.0', 1, 1, 1, 1, NULL
)
ON CONFLICT(partition_key) DO UPDATE SET
    namespace = excluded.namespace,
    canonical_filters = excluded.canonical_filters,
    capabilities_json = excluded.capabilities_json,
    status = excluded.status,
    response_key = excluded.response_key,
    endpoint = excluded.endpoint,
    fetched_at = excluded.fetched_at,
    validated_at = excluded.validated_at,
    fresh_until = excluded.fresh_until,
    retained_until = excluded.retained_until,
    row_count = excluded.row_count,
    known_cap = excluded.known_cap,
    projection_contract = excluded.projection_contract,
    failure_category = NULL
