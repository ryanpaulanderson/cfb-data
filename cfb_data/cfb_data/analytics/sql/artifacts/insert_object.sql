INSERT OR IGNORE INTO artifact_objects (
    content_digest, kind, codec_id, codec_version,
    manifest_json, first_seen_at
) VALUES (?, ?, ?, ?, ?, ?)
