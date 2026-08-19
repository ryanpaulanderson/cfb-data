BEGIN IMMEDIATE;

CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    recipe_id TEXT NOT NULL,
    recipe_revision INTEGER,
    recipe_kind TEXT NOT NULL CHECK (recipe_kind IN ('dataset', 'workflow')),
    parameter_fingerprint TEXT NOT NULL,
    graph_fingerprint TEXT NOT NULL,
    parent_run_id TEXT REFERENCES runs(run_id),
    source_behavior TEXT NOT NULL CHECK (
        source_behavior IN ('preserve_snapshot', 'normal_freshness', 'refresh')
    ),
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE run_transitions (
    transition_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    state TEXT NOT NULL CHECK (
        state IN ('created', 'running', 'completed', 'failed', 'cancelled')
    ),
    occurred_at TEXT NOT NULL,
    node_id TEXT,
    failure_category TEXT
) STRICT;
CREATE INDEX run_transitions_by_run
    ON run_transitions(run_id, transition_id);

CREATE TABLE node_transitions (
    transition_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    node_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN ('ready', 'running', 'reused', 'completed', 'failed', 'cancelled')
    ),
    occurred_at TEXT NOT NULL,
    failure_category TEXT
) STRICT;
CREATE INDEX node_transitions_by_node
    ON node_transitions(run_id, node_id, transition_id);

CREATE TABLE artifact_objects (
    content_digest TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    codec_id TEXT NOT NULL,
    codec_version INTEGER NOT NULL,
    manifest_json TEXT NOT NULL,
    first_seen_at TEXT NOT NULL
) STRICT;

CREATE TABLE node_artifact_bindings (
    binding_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    node_id TEXT NOT NULL,
    output_name TEXT NOT NULL,
    node_fingerprint TEXT NOT NULL,
    content_digest TEXT NOT NULL REFERENCES artifact_objects(content_digest),
    placement TEXT NOT NULL CHECK (placement IN ('coordinator', 'local', 'dask')),
    committed_at TEXT NOT NULL,
    UNIQUE (run_id, node_id, output_name)
) STRICT;
CREATE INDEX bindings_by_content
    ON node_artifact_bindings(content_digest);

CREATE TRIGGER runs_are_immutable_update
BEFORE UPDATE ON runs BEGIN SELECT RAISE(ABORT, 'runs are immutable'); END;
CREATE TRIGGER runs_are_immutable_delete
BEFORE DELETE ON runs BEGIN SELECT RAISE(ABORT, 'runs are immutable'); END;
CREATE TRIGGER run_transitions_are_immutable_update
BEFORE UPDATE ON run_transitions
BEGIN SELECT RAISE(ABORT, 'run transitions are immutable'); END;
CREATE TRIGGER run_transitions_are_immutable_delete
BEFORE DELETE ON run_transitions
BEGIN SELECT RAISE(ABORT, 'run transitions are immutable'); END;
CREATE TRIGGER node_transitions_are_immutable_update
BEFORE UPDATE ON node_transitions
BEGIN SELECT RAISE(ABORT, 'node transitions are immutable'); END;
CREATE TRIGGER node_transitions_are_immutable_delete
BEFORE DELETE ON node_transitions
BEGIN SELECT RAISE(ABORT, 'node transitions are immutable'); END;
CREATE TRIGGER artifact_objects_are_immutable_update
BEFORE UPDATE ON artifact_objects
BEGIN SELECT RAISE(ABORT, 'artifact objects are immutable'); END;
CREATE TRIGGER artifact_objects_are_immutable_delete
BEFORE DELETE ON artifact_objects
BEGIN SELECT RAISE(ABORT, 'artifact objects are immutable'); END;
CREATE TRIGGER bindings_are_immutable_update
BEFORE UPDATE ON node_artifact_bindings
BEGIN SELECT RAISE(ABORT, 'bindings are immutable'); END;
CREATE TRIGGER bindings_are_immutable_delete
BEFORE DELETE ON node_artifact_bindings
BEGIN SELECT RAISE(ABORT, 'bindings are immutable'); END;

PRAGMA user_version = 1;
COMMIT;
