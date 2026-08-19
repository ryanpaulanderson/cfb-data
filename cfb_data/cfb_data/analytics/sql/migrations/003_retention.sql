BEGIN IMMEDIATE;

CREATE TABLE run_retention_transitions (
    transition_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    state TEXT NOT NULL CHECK (state IN ('active', 'retired')),
    occurred_at TEXT NOT NULL
) STRICT;
CREATE INDEX retention_by_run
    ON run_retention_transitions(run_id, transition_id);
INSERT INTO run_retention_transitions (run_id, state, occurred_at)
    SELECT run_id, 'active', created_at FROM runs;

CREATE TABLE artifact_pin_transitions (
    transition_id INTEGER PRIMARY KEY,
    content_digest TEXT NOT NULL REFERENCES artifact_objects(content_digest),
    pin_name TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pinned', 'unpinned')),
    occurred_at TEXT NOT NULL
) STRICT;
CREATE INDEX pins_by_artifact
    ON artifact_pin_transitions(content_digest, pin_name, transition_id);

CREATE TABLE artifact_gc_transitions (
    transition_id INTEGER PRIMARY KEY,
    content_digest TEXT NOT NULL REFERENCES artifact_objects(content_digest),
    state TEXT NOT NULL CHECK (state IN ('deleting', 'deleted')),
    occurred_at TEXT NOT NULL
) STRICT;
CREATE INDEX gc_by_artifact
    ON artifact_gc_transitions(content_digest, transition_id);

CREATE TRIGGER retention_is_immutable_update
BEFORE UPDATE ON run_retention_transitions
BEGIN SELECT RAISE(ABORT, 'retention transitions are immutable'); END;
CREATE TRIGGER retention_is_immutable_delete
BEFORE DELETE ON run_retention_transitions
BEGIN SELECT RAISE(ABORT, 'retention transitions are immutable'); END;
CREATE TRIGGER pins_are_immutable_update
BEFORE UPDATE ON artifact_pin_transitions
BEGIN SELECT RAISE(ABORT, 'pin transitions are immutable'); END;
CREATE TRIGGER pins_are_immutable_delete
BEFORE DELETE ON artifact_pin_transitions
BEGIN SELECT RAISE(ABORT, 'pin transitions are immutable'); END;
CREATE TRIGGER gc_is_immutable_update
BEFORE UPDATE ON artifact_gc_transitions
BEGIN SELECT RAISE(ABORT, 'gc transitions are immutable'); END;
CREATE TRIGGER gc_is_immutable_delete
BEFORE DELETE ON artifact_gc_transitions
BEGIN SELECT RAISE(ABORT, 'gc transitions are immutable'); END;

PRAGMA user_version = 3;
COMMIT;
