BEGIN IMMEDIATE;

ALTER TABLE runs ADD COLUMN max_http_attempts INTEGER NOT NULL DEFAULT 100;

CREATE TABLE attempt_reservations (
    reservation_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    node_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    retry_number INTEGER NOT NULL CHECK (retry_number > 0),
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    reserved_at TEXT NOT NULL,
    UNIQUE (run_id, ordinal)
) STRICT;
CREATE INDEX attempts_by_run
    ON attempt_reservations(run_id, reservation_id);

CREATE TRIGGER attempts_are_immutable_update
BEFORE UPDATE ON attempt_reservations
BEGIN SELECT RAISE(ABORT, 'attempt reservations are immutable'); END;
CREATE TRIGGER attempts_are_immutable_delete
BEFORE DELETE ON attempt_reservations
BEGIN SELECT RAISE(ABORT, 'attempt reservations are immutable'); END;

PRAGMA user_version = 4;
COMMIT;
