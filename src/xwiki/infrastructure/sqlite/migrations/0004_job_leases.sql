-- UX-002B: lease-aware processing and retries. Never change the checksummed
-- ARCH-00B migrations or the existing Voice Memos recordings schema.
ALTER TABLE jobs ADD COLUMN model_key TEXT;
ALTER TABLE jobs ADD COLUMN lease_token TEXT;
ALTER TABLE jobs ADD COLUMN lease_expires_at REAL;
ALTER TABLE jobs ADD COLUMN retry_after REAL;
ALTER TABLE jobs ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0
  CHECK (attempt_count >= 0);
ALTER TABLE jobs ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 3
  CHECK (max_attempts >= 1 AND max_attempts <= 10);
ALTER TABLE jobs ADD COLUMN result_revision_id TEXT;

CREATE INDEX jobs_due_claim
  ON jobs(kind, model_key, status, retry_after, created_at);
CREATE INDEX jobs_expired_lease
  ON jobs(status, lease_expires_at);
