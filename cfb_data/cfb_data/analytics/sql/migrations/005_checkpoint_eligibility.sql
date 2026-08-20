BEGIN IMMEDIATE;

ALTER TABLE node_artifact_bindings
ADD COLUMN checkpoint_eligible INTEGER NOT NULL DEFAULT 1
CHECK (checkpoint_eligible IN (0, 1));

PRAGMA user_version = 5;
COMMIT;
