-- New private product store; does not touch legacy ingest.sqlite.
CREATE TABLE sources (
    source_id TEXT PRIMARY KEY NOT NULL,
    origin TEXT NOT NULL CHECK (origin IN ('voice_memo','file','markdown_vault','manual')),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    created_at TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN
        ('queued','stored','transcribing','indexed','failed_retryable','failed_terminal')),
    privacy_scope TEXT NOT NULL DEFAULT 'private' CHECK (privacy_scope = 'private'),
    captured_at TEXT,
    transcript_revision_id TEXT,
    language TEXT,
    audio_duration_ms INTEGER CHECK (audio_duration_ms IS NULL OR audio_duration_ms >= 0)
);
CREATE INDEX sources_by_hash ON sources(origin, content_sha256);
CREATE INDEX sources_by_status ON sources(status);

-- Retain the exact values of every legacy row, including paths and errors.
-- This table is PRIVATE and never part of JSON/domain/web exports.
-- A new row is appended if an old recording changes between imports.
CREATE TABLE legacy_recording_snapshots (
    recording_id TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL CHECK (length(snapshot_sha256) = 64),
    audio_sha256 TEXT NOT NULL,
    audio_path TEXT NOT NULL,
    raw_path TEXT,
    transcript_path TEXT,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    last_error TEXT,
    updated_at TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    source_id TEXT REFERENCES sources(source_id),
    PRIMARY KEY (recording_id, snapshot_sha256)
);
CREATE INDEX legacy_snapshots_by_source
    ON legacy_recording_snapshots(source_id);

-- All unconvertible rows remain in snapshots and are explicitly reported.
CREATE TABLE legacy_migration_issues (
    recording_id TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL,
    issue_code TEXT NOT NULL,
    PRIMARY KEY (recording_id, snapshot_sha256, issue_code),
    FOREIGN KEY (recording_id, snapshot_sha256)
        REFERENCES legacy_recording_snapshots(recording_id, snapshot_sha256)
);
