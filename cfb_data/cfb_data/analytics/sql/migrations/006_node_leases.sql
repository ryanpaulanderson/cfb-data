BEGIN IMMEDIATE;

CREATE TABLE node_execution_leases (
    lease_key TEXT PRIMARY KEY,
    owner_token TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    node_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
) STRICT;

CREATE INDEX node_leases_by_run
    ON node_execution_leases(run_id, node_id);

PRAGMA user_version = 6;
COMMIT;
