"""Lease, retry, CAS and schema migration tests against a real SQLite database."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from xwiki.domain.enums import SourceOrigin, SourceStatus
from xwiki.domain.source import Source, TranscriptRevision
from xwiki.infrastructure.sqlite.database import ConflictError, open_product_db
from xwiki.infrastructure.sqlite.job_repository import JobRepository, StaleLease
from xwiki.infrastructure.sqlite.repositories import ProductRepository

MODEL = "b" * 64
STAMP = "2026-11-03T00:00:00+00:00"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / ".state" / "product.sqlite"
    with closing(open_product_db(path)) as conn:
        ProductRepository(conn).save_source(
            Source(
                source_id="source-01", origin=SourceOrigin.FILE,
                content_sha256=hashlib.sha256(b"audio").hexdigest(),
                created_at=STAMP, imported_at=STAMP, status=SourceStatus.STORED,
            )
        )
    return path


def job(db_path: Path) -> JobRepository:
    return JobRepository(open_product_db(db_path))


def test_job_migration_preserves_old_job_history_and_is_repeatable(db_path: Path) -> None:
    with closing(open_product_db(db_path)) as conn:
        assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 4
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(jobs)")
        }
        assert {
            "lease_token", "lease_expires_at", "retry_after", "attempt_count",
            "max_attempts", "model_key", "result_revision_id",
        } <= columns
        old_columns = conn.execute(
            "PRAGMA table_info(job_attempts)"
        ).fetchall()
        assert old_columns
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_enqueue_idempotent_and_does_not_mutate_source(db_path: Path) -> None:
    with closing(open_product_db(db_path)) as conn:
        jobs = JobRepository(conn)
        first = jobs.enqueue("source-01", MODEL, now=1000)
        same = jobs.enqueue("source-01", MODEL, now=2000)
        assert first == same
        assert first.status == "queued"
        assert first.attempt_count == 0
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
        assert ProductRepository(conn).get_source("source-01").status is SourceStatus.STORED


def test_two_connections_cannot_claim_same_job(db_path: Path) -> None:
    with closing(open_product_db(db_path)) as one, closing(open_product_db(db_path)) as two:
        jobs1, jobs2 = JobRepository(one), JobRepository(two)
        pending = jobs1.enqueue("source-01", MODEL, now=1000)
        claimed = jobs1.claim(MODEL, now=1001, lease_seconds=30)
        assert claimed is not None
        assert claimed.job_id == pending.job_id
        assert jobs2.claim(MODEL, now=1002) is None
        assert jobs1.get(pending.job_id).attempt_count == 1


def test_expired_attempt_recovered_without_losing_original(db_path: Path) -> None:
    with closing(open_product_db(db_path)) as one:
        first = JobRepository(one)
        pending = first.enqueue("source-01", MODEL, now=1000)
        lease1 = first.claim(MODEL, now=1001, lease_seconds=3)
        assert lease1 is not None
    with closing(open_product_db(db_path)) as two:
        jobs = JobRepository(two)
        assert jobs.recover_expired(now=1002) == 0
        assert jobs.recover_expired(now=1005) == 1
        assert jobs.recover_expired(now=1006) == 0
        assert jobs.get(pending.job_id).status == "failed_retryable"
        lease2 = jobs.claim(MODEL, now=1007, lease_seconds=30)
        assert lease2 is not None and lease2.attempt_count == 2
        assert lease2.lease_token != lease1.lease_token
        revision = TranscriptRevision(
            "transcript-01", "source-01", hashlib.sha256(b"text").hexdigest(),
            "fake", MODEL, STAMP
        )
        with pytest.raises(StaleLease):
            jobs.complete(lease1, revision, now=1008)
        assert jobs.get(pending.job_id).status == "processing"
        assert jobs.get(pending.job_id).result_revision_id is None
        records = two.execute(
            "SELECT attempt_number,outcome FROM job_attempts ORDER BY attempt_number"
        ).fetchall()
        assert tuple(records[0]) == (1, "interrupted")
        assert tuple(records[1]) == (2, None)


def test_lease_renewal_prevents_recovery(db_path: Path) -> None:
    with closing(open_product_db(db_path)) as conn:
        jobs = JobRepository(conn)
        jobs.enqueue("source-01", MODEL, now=1000)
        lease = jobs.claim(MODEL, now=1001, lease_seconds=3)
        assert lease is not None
        assert jobs.renew(lease, now=1002, lease_seconds=5)
        assert jobs.recover_expired(now=1005) == 0
        assert jobs.claim(MODEL, now=1005) is None
        assert jobs.recover_expired(now=1008) == 1
        assert not jobs.renew(lease, now=1009)


def test_auto_retry_backoff_and_max_attempts(db_path: Path) -> None:
    with closing(open_product_db(db_path)) as conn:
        jobs = JobRepository(conn)
        pending = jobs.enqueue("source-01", MODEL, now=1000, max_attempts=2)
        first = jobs.claim(MODEL, now=1001)
        result = jobs.fail(first, "TRANSCRIBER_FAILED", retryable=True, now=1002)
        assert result.status == "failed_retryable"
        assert result.retry_after == 1017.0
        assert jobs.claim(MODEL, now=1016) is None
        second = jobs.claim(MODEL, now=1018)
        assert second is not None and second.attempt_count == 2
        ended = jobs.fail(second, "TRANSCRIBER_FAILED", retryable=True, now=1020)
        assert ended.status == "failed_terminal"
        assert jobs.claim(MODEL, now=10000) is None
        assert jobs.get(pending.job_id).attempt_count == 2


def test_explicit_retry_does_not_reset_attempts(db_path: Path) -> None:
    with closing(open_product_db(db_path)) as conn:
        jobs = JobRepository(conn)
        j = jobs.enqueue("source-01", MODEL, now=1000)
        first = jobs.claim(MODEL, now=1001)
        jobs.fail(first, "TRANSCRIBER_FAILED", retryable=True, now=1002)
        refreshed = jobs.retry(j.job_id, now=1003)
        assert refreshed.status == "queued"
        assert refreshed.attempt_count == 1
        second = jobs.claim(MODEL, now=1004)
        assert second is not None and second.attempt_count == 2
        with pytest.raises(ConflictError, match="retry"):
            jobs.retry(j.job_id)


def test_cancel_prevents_inflight_worker_committing(db_path: Path) -> None:
    with closing(open_product_db(db_path)) as conn:
        jobs = JobRepository(conn)
        pending = jobs.enqueue("source-01", MODEL, now=1000)
        claimed = jobs.claim(MODEL, now=1001)
        assert claimed is not None
        assert jobs.cancel(pending.job_id, now=1002).status == "cancelled"
        with pytest.raises(StaleLease):
            jobs.complete(
                claimed, TranscriptRevision("transcript-01", "source-01", "a" * 64,
                                            "fake", MODEL, STAMP),
                now=1003,
            )
        assert conn.execute("SELECT COUNT(*) FROM transcript_revisions").fetchone()[0] == 0


def test_completion_transaction_rolls_back_when_revision_insert_fails(db_path: Path) -> None:
    with closing(open_product_db(db_path)) as conn:
        jobs = JobRepository(conn)
        j = jobs.enqueue("source-01", MODEL, now=1000)
        lease = jobs.claim(MODEL, now=1001)
        conn.execute(
            """CREATE TRIGGER reject_revision BEFORE INSERT ON transcript_revisions
               BEGIN SELECT RAISE(ABORT, 'simulated disk failure'); END"""
        )
        with pytest.raises(sqlite3.IntegrityError):
            jobs.complete(
                lease,
                TranscriptRevision("transcript-01", "source-01", "a" * 64,
                                   "fake", MODEL, STAMP),
                now=1002,
            )
        assert jobs.get(j.job_id).status == "processing"
        assert jobs.get(j.job_id).result_revision_id is None
        assert ProductRepository(conn).get_source("source-01").transcript_revision_id is None
        assert conn.execute("SELECT COUNT(*) FROM transcript_revisions").fetchone()[0] == 0
        conn.execute("DROP TRIGGER reject_revision")
        assert jobs.recover_expired(now=2000) == 1
        assert jobs.claim(MODEL, now=2001) is not None


def test_no_transcription_job_for_unverified_historical_record(db_path: Path) -> None:
    with closing(open_product_db(db_path)) as conn:
        repo = ProductRepository(conn)
        repo.save_source(
            Source(
                source_id="legacy-one", origin=SourceOrigin.VOICE_MEMO,
                content_sha256="a" * 64, created_at=STAMP, imported_at=STAMP,
                status=SourceStatus.QUEUED,
            )
        )
        with pytest.raises(Exception, match="stored"):
            JobRepository(conn).enqueue("legacy-one", MODEL)
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
