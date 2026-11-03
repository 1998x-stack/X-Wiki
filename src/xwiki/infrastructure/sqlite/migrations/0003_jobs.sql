-- The new job queue is separate from legacy recordings.status.
CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    kind TEXT NOT NULL CHECK (kind IN ('import','transcribe','index','propose')),
    status TEXT NOT NULL CHECK (status IN
        ('queued','processing','completed','failed_retryable','failed_terminal','cancelled')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error_code TEXT,
    idempotency_key TEXT NOT NULL UNIQUE
);
CREATE INDEX jobs_by_status ON jobs(status, updated_at);

CREATE TABLE job_attempts (
    attempt_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    outcome TEXT,
    error_code TEXT,
    UNIQUE(job_id, attempt_number)
);
