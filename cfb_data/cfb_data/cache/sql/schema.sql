CREATE TABLE IF NOT EXISTS cache_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS response_records (
    key TEXT PRIMARY KEY,
    endpoint TEXT NOT NULL,
    response_contract TEXT NOT NULL,
    body BLOB NOT NULL,
    fetched_at TEXT NOT NULL,
    fresh_until TEXT NOT NULL,
    retained_until TEXT NOT NULL,
    etag TEXT,
    last_modified TEXT,
    row_count INTEGER NOT NULL CHECK (row_count >= 0)
) STRICT;
CREATE TABLE IF NOT EXISTS catalog_observations (
    namespace TEXT NOT NULL,
    grain TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (namespace, grain)
) STRICT;
CREATE INDEX IF NOT EXISTS response_retention_idx
ON response_records(retained_until);
CREATE TABLE IF NOT EXISTS refresh_leases (
    key TEXT PRIMARY KEY,
    owner_token TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY,
    school TEXT NOT NULL,
    normalized_school TEXT NOT NULL,
    abbreviation TEXT,
    normalized_abbreviation TEXT,
    alternate_names_json TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS team_school_idx ON teams(normalized_school);
CREATE INDEX IF NOT EXISTS team_abbreviation_idx ON teams(normalized_abbreviation);
CREATE TABLE IF NOT EXISTS team_aliases (
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    PRIMARY KEY (team_id, normalized_alias)
) STRICT;
CREATE INDEX IF NOT EXISTS team_alias_idx ON team_aliases(normalized_alias);
CREATE TABLE IF NOT EXISTS team_seasons (
    team_id INTEGER NOT NULL,
    season INTEGER NOT NULL,
    conference_name TEXT,
    venue_id INTEGER,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (team_id, season)
) STRICT;
CREATE TABLE IF NOT EXISTS conferences (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    abbreviation TEXT,
    normalized_abbreviation TEXT,
    classification TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS conference_name_idx ON conferences(normalized_name);
CREATE INDEX IF NOT EXISTS conference_abbreviation_idx
ON conferences(normalized_abbreviation);
CREATE TABLE IF NOT EXISTS conference_affiliations (
    team_id INTEGER NOT NULL,
    conference_id INTEGER NOT NULL,
    start_year INTEGER NOT NULL,
    end_year INTEGER,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (team_id, conference_id, start_year)
) STRICT;
CREATE TABLE IF NOT EXISTS venues (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    city TEXT,
    state TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS venue_name_idx ON venues(normalized_name);
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY,
    season INTEGER,
    week INTEGER,
    season_type TEXT,
    start_date TEXT,
    status TEXT,
    home_team_id INTEGER,
    away_team_id INTEGER,
    venue_id INTEGER,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS game_partition_idx ON games(season, week);
CREATE TABLE IF NOT EXISTS athletes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    position TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS athlete_name_idx ON athletes(normalized_name);
CREATE TABLE IF NOT EXISTS athlete_team_seasons (
    athlete_id TEXT NOT NULL,
    team_name TEXT NOT NULL,
    normalized_team_name TEXT NOT NULL,
    season INTEGER NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (athlete_id, normalized_team_name, season)
) STRICT;
CREATE TABLE IF NOT EXISTS recruits (
    id TEXT PRIMARY KEY,
    athlete_id TEXT,
    name TEXT NOT NULL,
    year INTEGER,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS coaches (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    wikidata_id TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS coach_team_seasons (
    coach_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    start_year INTEGER NOT NULL,
    end_year INTEGER,
    tenure_id INTEGER,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (coach_id, team_id, start_year)
) STRICT;
CREATE TABLE IF NOT EXISTS drives (
    id TEXT PRIMARY KEY,
    game_id INTEGER NOT NULL,
    offense_team_id INTEGER,
    offense_team TEXT,
    defense_team_id INTEGER,
    defense_team TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS plays (
    id TEXT PRIMARY KEY,
    game_id INTEGER NOT NULL,
    drive_id TEXT,
    play_type_id INTEGER,
    play_type TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS vocabularies (
    namespace TEXT NOT NULL,
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    abbreviation TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL,
    PRIMARY KEY (namespace, id)
) STRICT;
CREATE TABLE IF NOT EXISTS playoff_matchups (
    id INTEGER PRIMARY KEY,
    season INTEGER,
    linked_game_id INTEGER,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS coverage (
    partition_key TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,
    canonical_filters TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,
    status TEXT NOT NULL,
    response_key TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    validated_at TEXT NOT NULL,
    fresh_until TEXT NOT NULL,
    retained_until TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    known_cap INTEGER,
    projection_contract TEXT NOT NULL,
    api_version TEXT NOT NULL,
    cache_key_version INTEGER NOT NULL,
    response_contract_version INTEGER NOT NULL,
    projector_version INTEGER NOT NULL,
    catalog_schema_version INTEGER NOT NULL,
    failure_category TEXT
) STRICT;
CREATE INDEX IF NOT EXISTS coverage_namespace_idx ON coverage(namespace);
CREATE TABLE IF NOT EXISTS coverage_failures (
    partition_key TEXT PRIMARY KEY,
    endpoint TEXT NOT NULL,
    canonical_filters TEXT NOT NULL,
    failure_category TEXT NOT NULL,
    failed_at TEXT NOT NULL
) STRICT;
