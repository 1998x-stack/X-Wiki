"""Crash-recoverable SQLite transcription jobs with atomic claims and leases.

No AI model calls, source deletion, Git publishing, or network endpoints.
Every state transition is conditional on the current lease token and transaction.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from xwiki.domain.errors import ContractError
from xwiki.domain.source import TranscriptRevision
from xwiki.domain.validation import digest, identifier
from xwiki.infrastructure.sqlite.database import ConflictError

ERROR_CODES = frozenset(
    {
        "TRANSCRIBER_UNAVAILABLE",
        "MODEL_NOT_FOUND",
        "INVALID_TRANSCRIPT",
        "SOURCE_MISSING",
        "SOURCE_CORRUPT",
        "TRANSCRIBER_FAILED",
        "TRANSCRIPT_STORAGE_FAILED",
        "UNEXPECTED_FAILURE",
        "WORKER_INTERRUPTED",
    }
)


class StaleLease(ConflictError):
    """Worker no longer has the right to commit a result."""


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    job_id: str
    source_id: str
    model_key: str
    status: str
    attempt_count: int
    max_attempts: int
    result_revision_id: str | None
    error_code: str | None
    retry_after: float | None


@dataclass(frozen=True, slots=True)
class JobLease:
    job_id: str
    source_id: str
    model_key: str
    lease_token: str
    attempt_id: str
    attempt_count: int
    lease_expires_at: float


def utc_at(now: float) -> str:
    return datetime.fromtimestamp(now, timezone.utc).isoformat()


class JobRepository:
    """One repository per SQLite connection (WAL + foreign keys are mandatory).

    Transcription jobs only. Existing ARCH-00B rows for other kinds are untouched.
    Methods use BEGIN IMMEDIATE and short transactions so two workers cannot
    claim the same job. Leases are wall-clock timestamps to survive reboots.
    """

    def __init__(self, connection: sqlite3.Connection):
        self.db = connection

    def get(self, job_id: str) -> JobSnapshot | None:
        identifier(job_id, "job_id")
        row = self.db.execute(
            """SELECT job_id,source_id,model_key,status,attempt_count,max_attempts,
                      result_revision_id,error_code,retry_after
               FROM jobs WHERE job_id=?""",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        return JobSnapshot(**dict(row))

    def enqueue(self, source_id: str, model_key: str, *, now: float | None = None,
                max_attempts: int = 3) -> JobSnapshot:
        identifier(source_id, "source_id")
        digest(model_key, "model_key")
        if type(max_attempts) is not int or not 1 <= max_attempts <= 10:
            raise ContractError("max_attempts must be an integer from 1 to 10")
        instant = time.time() if now is None else now
        key = hashlib.sha256(
            ("transcribe\0" + source_id + "\0" + model_key).encode()
        ).hexdigest()
        job_id = "job-" + key[:32]
        self.db.execute("BEGIN IMMEDIATE")
        try:
            parent = self.db.execute(
                "SELECT status FROM sources WHERE source_id=?", (source_id,)
            ).fetchone()
            if parent is None or parent["status"] not in {"stored", "transcribing"}:
                raise ContractError("transcription requires a verified stored source")
            self.db.execute(
                """INSERT INTO jobs(job_id,source_id,kind,status,created_at,updated_at,
                                    idempotency_key,model_key,max_attempts)
                   VALUES(?,?,'transcribe','queued',?,?,?,?,?)
                   ON CONFLICT(idempotency_key) DO NOTHING""",
                (job_id, source_id, utc_at(instant), utc_at(instant), key,
                 model_key, max_attempts),
            )
            record = self.get(job_id)
            if record is None or record.source_id != source_id or record.model_key != model_key:
                raise ConflictError("job idempotency key collision")
            self.db.execute("COMMIT")
            return record
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _recover_locked(self, now: float) -> int:
        expired = self.db.execute(
            """SELECT job_id,attempt_count,max_attempts
               FROM jobs WHERE kind='transcribe' AND status='processing'
               AND lease_expires_at <= ?""", (now,)
        ).fetchall()
        for row in expired:
            terminal = row["attempt_count"] >= row["max_attempts"]
            self.db.execute(
                """UPDATE jobs SET status=?,error_code='WORKER_INTERRUPTED',
                   retry_after=NULL,lease_token=NULL,lease_expires_at=NULL,
                   updated_at=? WHERE job_id=?""",
                ("failed_terminal" if terminal else "failed_retryable",
                 utc_at(now), row["job_id"]),
            )
            self.db.execute(
                """UPDATE job_attempts SET finished_at=?,outcome='interrupted',
                   error_code='WORKER_INTERRUPTED'
                   WHERE job_id=? AND finished_at IS NULL""",
                (utc_at(now), row["job_id"]),
            )
        return len(expired)

    def recover_expired(self, *, now: float | None = None) -> int:
        instant = time.time() if now is None else now
        self.db.execute("BEGIN IMMEDIATE")
        try:
            count = self._recover_locked(instant)
            self.db.execute("COMMIT")
            return count
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def claim(self, model_key: str, *, now: float | None = None,
              lease_seconds: float = 180.0) -> JobLease | None:
        digest(model_key, "model_key")
        if lease_seconds < 3:
            raise ContractError("lease_seconds must be >=3 seconds")
        instant = time.time() if now is None else now
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self._recover_locked(instant)
            row = self.db.execute(
                """SELECT job_id,source_id,attempt_count FROM jobs
                   WHERE kind='transcribe' AND model_key=?
                     AND status IN ('queued','failed_retryable')
                     AND (retry_after IS NULL OR retry_after<=?)
                     AND attempt_count < max_attempts
                   ORDER BY created_at,job_id LIMIT 1""",
                (model_key, instant),
            ).fetchone()
            if row is None:
                self.db.execute("COMMIT")
                return None
            attempt = row["attempt_count"] + 1
            token = uuid.uuid4().hex
            attempt_id = "attempt-" + uuid.uuid4().hex
            expiry = instant + lease_seconds
            self.db.execute(
                """UPDATE jobs SET status='processing',attempt_count=?,
                   lease_token=?,lease_expires_at=?,retry_after=NULL,error_code=NULL,
                   updated_at=? WHERE job_id=?""",
                (attempt, token, expiry, utc_at(instant), row["job_id"]),
            )
            self.db.execute(
                """INSERT INTO job_attempts(attempt_id,job_id,attempt_number,started_at)
                   VALUES(?,?,?,?)""",
                (attempt_id, row["job_id"], attempt, utc_at(instant)),
            )
            self.db.execute("COMMIT")
            return JobLease(
                row["job_id"], row["source_id"], model_key, token,
                attempt_id, attempt, expiry
            )
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _assert_lease(self, lease: JobLease, instant: float) -> None:
        row = self.db.execute(
            """SELECT status,lease_token,lease_expires_at FROM jobs WHERE job_id=?""",
            (lease.job_id,),
        ).fetchone()
        if (
            row is None or row["status"] != "processing"
            or row["lease_token"] != lease.lease_token
            or row["lease_expires_at"] is None
            or row["lease_expires_at"] <= instant
        ):
            raise StaleLease("processing lease was lost or expired")

    def renew(self, lease: JobLease, *, now: float | None = None,
              lease_seconds: float = 180.0) -> bool:
        instant = time.time() if now is None else now
        if lease_seconds < 3:
            raise ContractError("lease_seconds must be >=3 seconds")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            try:
                self._assert_lease(lease, instant)
            except StaleLease:
                self.db.execute("COMMIT")
                return False
            self.db.execute(
                "UPDATE jobs SET lease_expires_at=?,updated_at=? WHERE job_id=?",
                (instant + lease_seconds, utc_at(instant), lease.job_id),
            )
            self.db.execute("COMMIT")
            return True
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def complete(self, lease: JobLease, revision: TranscriptRevision,
                 *, now: float | None = None) -> None:
        instant = time.time() if now is None else now
        if lease.source_id != revision.source_id or lease.model_key != revision.model:
            raise ContractError("transcript identity does not match claimed source/model")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self._assert_lease(lease, instant)
            self.db.execute(
                """INSERT INTO transcript_revisions(
                       revision_id,source_id,text_sha256,engine,model,created_at
                   ) VALUES(?,?,?,?,?,?)
                   ON CONFLICT(revision_id) DO NOTHING""",
                (
                    revision.revision_id, revision.source_id, revision.text_sha256,
                    revision.engine, revision.model, revision.created_at,
                ),
            )
            record = self.db.execute(
                """SELECT source_id,text_sha256,engine,model FROM transcript_revisions
                   WHERE revision_id=?""", (revision.revision_id,)
            ).fetchone()
            if record is None or tuple(record) != (
                revision.source_id, revision.text_sha256,
                revision.engine, revision.model
            ):
                raise ConflictError("transcript ID already identifies different content")
            self.db.execute(
                "UPDATE sources SET transcript_revision_id=? WHERE source_id=?",
                (revision.revision_id, revision.source_id),
            )
            self.db.execute(
                """UPDATE jobs SET status='completed',result_revision_id=?,
                   lease_token=NULL,lease_expires_at=NULL,retry_after=NULL,
                   error_code=NULL,updated_at=? WHERE job_id=?""",
                (revision.revision_id, utc_at(instant), lease.job_id),
            )
            self.db.execute(
                """UPDATE job_attempts SET finished_at=?,outcome='completed',
                   error_code=NULL WHERE attempt_id=? AND finished_at IS NULL""",
                (utc_at(instant), lease.attempt_id),
            )
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def fail(self, lease: JobLease, code: str, *, retryable: bool,
             now: float | None = None) -> JobSnapshot:
        if code not in ERROR_CODES:
            raise ContractError("unknown sanitized transcription error code")
        instant = time.time() if now is None else now
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self._assert_lease(lease, instant)
            row = self.db.execute(
                "SELECT attempt_count,max_attempts FROM jobs WHERE job_id=?",
                (lease.job_id,),
            ).fetchone()
            can_retry = retryable and row["attempt_count"] < row["max_attempts"]
            delay = min(3600.0, 15.0 * 2 ** (row["attempt_count"] - 1))
            self.db.execute(
                """UPDATE jobs SET status=?,error_code=?,retry_after=?,
                   lease_token=NULL,lease_expires_at=NULL,updated_at=?
                   WHERE job_id=?""",
                (
                    "failed_retryable" if can_retry else "failed_terminal",
                    code, instant + delay if can_retry else None,
                    utc_at(instant), lease.job_id,
                ),
            )
            self.db.execute(
                """UPDATE job_attempts SET finished_at=?,outcome=?,error_code=?
                   WHERE attempt_id=? AND finished_at IS NULL""",
                (utc_at(instant), "failed", code, lease.attempt_id),
            )
            self.db.execute("COMMIT")
            return self.get(lease.job_id)
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def retry(self, job_id: str, *, now: float | None = None) -> JobSnapshot:
        identifier(job_id, "job_id")
        instant = time.time() if now is None else now
        self.db.execute("BEGIN IMMEDIATE")
        try:
            cur = self.db.execute(
                """UPDATE jobs SET status='queued',retry_after=NULL,
                   error_code=NULL,updated_at=? WHERE job_id=?
                   AND status='failed_retryable' AND attempt_count<max_attempts""",
                (utc_at(instant), job_id),
            )
            if cur.rowcount != 1:
                raise ConflictError("job is not eligible for retry")
            self.db.execute("COMMIT")
            return self.get(job_id)
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def cancel(self, job_id: str, *, now: float | None = None) -> JobSnapshot:
        identifier(job_id, "job_id")
        instant = time.time() if now is None else now
        self.db.execute("BEGIN IMMEDIATE")
        try:
            cur = self.db.execute(
                """UPDATE jobs SET status='cancelled',retry_after=NULL,
                   lease_token=NULL,lease_expires_at=NULL,updated_at=?
                   WHERE job_id=? AND status IN ('queued','processing','failed_retryable')""",
                (utc_at(instant), job_id),
            )
            if cur.rowcount != 1:
                raise ConflictError("job is not cancellable")
            self.db.execute(
                """UPDATE job_attempts SET finished_at=?,outcome='cancelled'
                   WHERE job_id=? AND finished_at IS NULL""",
                (utc_at(instant), job_id),
            )
            self.db.execute("COMMIT")
            return self.get(job_id)
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
