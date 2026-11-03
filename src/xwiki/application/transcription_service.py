"""UX-002B durable, local transcription use case.

Source bytes remain immutable. Model output is fsynced to a separate private
blob store before a single SQLite transaction publishes revision and job status.
Crashes can leave harmless unreferenced blobs, never a false completed job.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from xwiki.domain.errors import ContractError
from xwiki.domain.source import TranscriptRevision
from xwiki.infrastructure.file_store import BlobError, PrivateBlobStore
from xwiki.infrastructure.sqlite.database import open_product_db
from xwiki.infrastructure.sqlite.job_repository import (
    JobLease,
    JobRepository,
    JobSnapshot,
    StaleLease,
)
from xwiki.infrastructure.sqlite.repositories import ProductRepository
from xwiki.infrastructure.whisper_adapter import (
    InvalidTranscript,
    TranscriptionFailure,
)


class TranscriptStorageFailure(TranscriptionFailure):
    code = "TRANSCRIPT_STORAGE_FAILED"
    retryable = True


class Transcriber(Protocol):
    model_key: str
    engine: str

    def transcribe(self, source_path: Path) -> str: ...


@dataclass(frozen=True, slots=True)
class RunResult:
    job_id: str
    status: str
    error_code: str | None
    revision_id: str | None


class TranscriptionService:
    """Single-job service; each DB operation opens a fresh short-lived connection.

    A lease-renewal thread has its own SQLite connection so a slow native
    transcriber does not make another worker steal the same active job.
    The process can be killed at any point; next invocation recovers expired
    leases and retries, retaining all previously imported originals.
    """

    def __init__(
        self,
        database_path: Path,
        source_blobs: PrivateBlobStore,
        transcript_blobs: PrivateBlobStore,
        transcriber: Transcriber,
        *,
        lease_seconds: float = 180.0,
    ):
        if lease_seconds < 3:
            raise ContractError("lease_seconds must be >=3")
        self.database_path = Path(database_path)
        self.sources = source_blobs
        self.transcripts = transcript_blobs
        self.transcriber = transcriber
        self.lease_seconds = lease_seconds

    def enqueue(self, source_id: str, *, max_attempts: int = 3) -> JobSnapshot:
        with closing(open_product_db(self.database_path)) as connection:
            source = ProductRepository(connection).get_source(source_id)
            if source is None or source.status.value != "stored":
                raise ContractError("source must be securely stored before transcription")
            self.sources.verify_blob(source.content_sha256)
            if not self.sources.is_audio(source.content_sha256):
                raise ContractError("text sources do not need audio transcription")
            return JobRepository(connection).enqueue(
                source_id, self.transcriber.model_key, max_attempts=max_attempts
            )

    def get(self, job_id: str) -> JobSnapshot | None:
        with closing(open_product_db(self.database_path)) as connection:
            return JobRepository(connection).get(job_id)

    def retry(self, job_id: str) -> JobSnapshot:
        with closing(open_product_db(self.database_path)) as connection:
            return JobRepository(connection).retry(job_id)

    def cancel(self, job_id: str) -> JobSnapshot:
        with closing(open_product_db(self.database_path)) as connection:
            return JobRepository(connection).cancel(job_id)

    def recover(self) -> int:
        with closing(open_product_db(self.database_path)) as connection:
            return JobRepository(connection).recover_expired()

    def _heartbeat(
        self, lease: JobLease, stop: threading.Event, lost: threading.Event
    ) -> None:
        interval = max(1.0, self.lease_seconds / 3)
        while not stop.wait(interval):
            try:
                with closing(open_product_db(self.database_path)) as connection:
                    if not JobRepository(connection).renew(
                        lease, lease_seconds=self.lease_seconds
                    ):
                        lost.set()
                        return
            except (OSError, sqlite3.Error, RuntimeError):
                lost.set()
                return

    def _run_claimed(self, lease: JobLease) -> TranscriptRevision:
        with closing(open_product_db(self.database_path)) as connection:
            source = ProductRepository(connection).get_source(lease.source_id)
        if source is None:
            raise BlobError("stored source metadata is missing")
        source_path = self.sources.verified_path(source.content_sha256)
        if not self.sources.is_audio(source.content_sha256):
            raise InvalidTranscript("source is not supported audio")
        result = self.transcriber.transcribe(source_path)
        if not isinstance(result, str) or not result.strip():
            raise InvalidTranscript("transcriber returned empty or non-text output")
        data = result.encode("utf-8")
        if len(data) > 16 * 1024 * 1024:
            raise InvalidTranscript("transcript exceeds safe text size limit")
        # Source may have changed while the native model was running; do not
        # approve an output for bytes that no longer match the Source hash.
        self.sources.verify_blob(source.content_sha256)
        try:
            receipt = self.transcripts.put_text(result)
        except (BlobError, OSError) as error:
            raise TranscriptStorageFailure("local transcript write failed") from error
        revision_id = "transcript-" + hashlib.sha256(
            (lease.source_id + "\0" + lease.model_key + "\0" + receipt.content_sha256)
            .encode("utf-8")
        ).hexdigest()[:32]
        return TranscriptRevision(
            revision_id, lease.source_id, receipt.content_sha256,
            self.transcriber.engine, lease.model_key,
            datetime.now(timezone.utc).isoformat(),
        )

    def run_once(self) -> RunResult | None:
        with closing(open_product_db(self.database_path)) as connection:
            lease = JobRepository(connection).claim(
                self.transcriber.model_key, lease_seconds=self.lease_seconds
            )
        if lease is None:
            return None
        stop = threading.Event()
        lost = threading.Event()
        thread = threading.Thread(
            target=self._heartbeat, args=(lease, stop, lost), daemon=True
        )
        thread.start()
        revision: TranscriptRevision | None = None
        code: str | None = None
        retryable = False
        try:
            try:
                revision = self._run_claimed(lease)
            except BlobError as error:
                code = "SOURCE_CORRUPT" if "SHA-256" in str(error) else "SOURCE_MISSING"
            except TranscriptionFailure as error:
                code = error.code
                retryable = error.retryable
            except (OSError, sqlite3.Error):
                code = "TRANSCRIBER_FAILED"
                retryable = True
            except Exception:
                # No sensitive exception messages, local filenames or model output
                # are persisted to the job or returned to the CLI.
                code = "UNEXPECTED_FAILURE"
                retryable = True
        finally:
            stop.set()
            thread.join(timeout=max(2.0, self.lease_seconds / 3 + 1))
        if lost.is_set():
            raise StaleLease("worker lost the processing lease; result was not committed")
        with closing(open_product_db(self.database_path)) as connection:
            jobs = JobRepository(connection)
            if revision is not None:
                # Verify saved text again immediately before SQLite references it.
                self.transcripts.verify_blob(revision.text_sha256)
                jobs.complete(lease, revision)
                return RunResult(lease.job_id, "completed", None, revision.revision_id)
            assert code is not None
            snapshot = jobs.fail(lease, code, retryable=retryable)
            return RunResult(
                lease.job_id, snapshot.status, snapshot.error_code, None
            )
