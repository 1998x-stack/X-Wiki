"""Real local file and SQLite integration; native ASR is injected for CI."""

from __future__ import annotations

import json
import threading
from contextlib import closing
from pathlib import Path

import pytest

from xwiki.application.import_source import ImportSource
from xwiki.application.transcription_service import TranscriptionService
from xwiki.domain.enums import SourceStatus
from xwiki.domain.errors import ContractError
from xwiki.infrastructure.file_store import PrivateBlobStore
from xwiki.infrastructure.sqlite.database import ConflictError, open_product_db
from xwiki.infrastructure.sqlite.job_repository import JobRepository
from xwiki.infrastructure.sqlite.repositories import ProductRepository
from xwiki.infrastructure.whisper_adapter import (
    LocalMLXWhisper,
    PlatformUnavailable,
    TranscriptionFailure,
)
from xwiki.interfaces.jobs_cli import main as jobs_cli

MODEL = "b" * 64
AUDIO = b"RIFF" + (40).to_bytes(4, "little") + b"WAVEfmt " + b"\0" * 32


class FakeLocalModel:
    model_key = MODEL
    engine = "mlx-whisper"

    def __init__(self, *, failures: int = 0, terminal: bool = False):
        self.runs = 0
        self.failures = failures
        self.terminal = terminal

    def transcribe(self, source_path: Path) -> str:
        assert source_path.is_file()
        self.runs += 1
        if self.terminal:
            raise PlatformUnavailable("simulated unsupported native runtime")
        if self.runs <= self.failures:
            raise TranscriptionFailure("transient synthetic native error")
        return "你好,新的想法。🙂\n"


@pytest.fixture
def local(tmp_path: Path):
    database = tmp_path / ".state" / "product.sqlite"
    sources = PrivateBlobStore(tmp_path / ".state" / "source-store")
    transcripts = PrivateBlobStore(tmp_path / ".state" / "transcript-store")
    model = FakeLocalModel()
    service = TranscriptionService(database, sources, transcripts, model)
    original = tmp_path / "my-memo.wav"
    original.write_bytes(AUDIO)
    with closing(open_product_db(database)) as db:
        imported = ImportSource(ProductRepository(db), sources).execute(original)
    return database, sources, transcripts, model, service, imported.source, original


def test_real_audio_processing_persists_transcript_without_publishing(local) -> None:
    database, sources, transcripts, model, service, source, original = local
    job = service.enqueue(source.source_id)
    assert job.status == "queued"
    assert job.attempt_count == 0
    assert service.enqueue(source.source_id) == job
    done = service.run_once()
    assert done is not None and done.status == "completed"
    assert done.revision_id is not None
    assert service.run_once() is None
    assert model.runs == 1
    with closing(open_product_db(database)) as db:
        repo = ProductRepository(db)
        saved = repo.get_source(source.source_id)
        assert saved.status is SourceStatus.STORED
        assert saved.transcript_revision_id == done.revision_id
        rev = repo.get_transcript_revision(done.revision_id)
        assert rev is not None and rev.model == MODEL
        assert rev.source_id == source.source_id
        assert transcripts.read_verified(rev.text_sha256).decode() == "你好,新的想法。🙂\n"
        assert db.execute("SELECT COUNT(*) FROM transcript_revisions").fetchone()[0] == 1
        assert tuple(db.execute(
            "SELECT attempt_number,outcome FROM job_attempts"
        ).fetchone()) == (1, "completed")
    assert original.read_bytes() == AUDIO
    assert sources.verify_blob(source.content_sha256) == len(AUDIO)


def test_completed_job_survives_reboot_and_does_not_run_again(local) -> None:
    database, sources, transcripts, _, service, source, _ = local
    service.enqueue(source.source_id)
    first = service.run_once()
    restarted = TranscriptionService(database, sources, transcripts, FakeLocalModel())
    assert restarted.enqueue(source.source_id).status == "completed"
    assert restarted.run_once() is None
    assert restarted.get(first.job_id).result_revision_id == first.revision_id


def test_text_document_is_preserved_but_never_enqueued_for_asr(local, tmp_path: Path) -> None:
    database, sources, _, _, service, _source, _ = local
    text = tmp_path / "my-note.md"
    text.write_text("# Notes\nThis is not audio.\n", encoding="utf-8")
    with closing(open_product_db(database)) as db:
        imported = ImportSource(ProductRepository(db), sources).execute(text)
    with pytest.raises(ContractError, match="text sources"):
        service.enqueue(imported.source.source_id)
    assert service.run_once() is None


def test_retryable_failure_is_sanitized_then_explicitly_retried(local) -> None:
    database, sources, transcripts, _, _, source, _ = local
    model = FakeLocalModel(failures=1)
    service = TranscriptionService(database, sources, transcripts, model)
    pending = service.enqueue(source.source_id)
    failure = service.run_once()
    assert failure is not None and failure.status == "failed_retryable"
    assert failure.error_code == "TRANSCRIBER_FAILED"
    assert service.get(pending.job_id).attempt_count == 1
    assert service.run_once() is None  # retry is delayed
    assert service.retry(pending.job_id).status == "queued"
    done = service.run_once()
    assert done is not None and done.status == "completed"
    assert model.runs == 2
    with closing(open_product_db(database)) as db:
        assert db.execute("SELECT COUNT(*) FROM job_attempts").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM transcript_revisions").fetchone()[0] == 1


def test_terminal_failure_never_deletes_original_and_requires_new_model(local) -> None:
    database, sources, transcripts, _, _, source, _ = local
    bad = TranscriptionService(
        database, sources, transcripts, FakeLocalModel(terminal=True)
    )
    job = bad.enqueue(source.source_id)
    finished = bad.run_once()
    assert finished is not None and finished.status == "failed_terminal"
    assert finished.error_code == "TRANSCRIBER_UNAVAILABLE"
    with pytest.raises(ConflictError, match="retry"):
        bad.retry(job.job_id)
    assert bad.get(job.job_id).result_revision_id is None
    assert sources.verify_blob(source.content_sha256) == len(AUDIO)


def test_corrupt_original_prevents_transcription_and_keeps_job_truthful(local) -> None:
    database, sources, _, model, service, source, _ = local
    job = service.enqueue(source.source_id)
    sources._blob_path(source.content_sha256).write_bytes(b"corruption")
    result = service.run_once()
    assert result is not None and result.status == "failed_terminal"
    assert result.error_code == "SOURCE_CORRUPT"
    assert model.runs == 0
    with closing(open_product_db(database)) as db:
        assert ProductRepository(db).get_source(source.source_id).transcript_revision_id is None
        assert db.execute("SELECT COUNT(*) FROM transcript_revisions").fetchone()[0] == 0
    assert service.get(job.job_id).status == "failed_terminal"


def test_cancelled_job_cannot_run_and_does_not_delete_source(local) -> None:
    _, sources, _, model, service, source, _ = local
    job = service.enqueue(source.source_id)
    assert service.cancel(job.job_id).status == "cancelled"
    assert service.run_once() is None
    assert model.runs == 0
    assert sources.verify_blob(source.content_sha256) > 0


def test_two_worker_instances_do_not_repeat_one_inflight_model_call(local) -> None:
    database, sources, transcripts, _, _, source, _ = local
    started = threading.Event()
    finished = threading.Event()

    class BlockingModel(FakeLocalModel):
        def transcribe(self, path: Path) -> str:
            started.set()
            assert finished.wait(10)
            return super().transcribe(path)

    model = BlockingModel()
    primary = TranscriptionService(database, sources, transcripts, model)
    secondary = TranscriptionService(database, sources, transcripts, FakeLocalModel())
    primary.enqueue(source.source_id)
    result = []
    thread = threading.Thread(target=lambda: result.append(primary.run_once()))
    thread.start()
    try:
        assert started.wait(10)
        assert secondary.run_once() is None
    finally:
        finished.set()
        thread.join(timeout=10)
    assert len(result) == 1 and result[0].status == "completed"
    assert model.runs == 1


def test_crashed_uncommitted_attempt_recovers_using_existing_private_bytes(local) -> None:
    database, sources, _, _, service, source, _ = local
    pending = service.enqueue(source.source_id)
    with closing(open_product_db(database)) as db:
        jobs = JobRepository(db)
        lease = jobs.claim(MODEL, now=100, lease_seconds=3)
        assert lease is not None
        assert jobs.get(pending.job_id).status == "processing"
    with closing(open_product_db(database)) as db:
        assert JobRepository(db).recover_expired(now=105) == 1
    # Service's next attempt writes same content-addressed transcript only once.
    done = service.run_once()
    assert done is not None and done.status == "completed"
    assert sources.verify_blob(source.content_sha256) == len(AUDIO)
    with closing(open_product_db(database)) as db:
        assert db.execute("SELECT COUNT(*) FROM job_attempts").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM transcript_revisions").fetchone()[0] == 1


def test_lease_expiry_or_write_failure_never_reports_false_completed(local, monkeypatch) -> None:
    database, sources, transcripts, _, service, source, _ = local
    pending = service.enqueue(source.source_id)
    original_complete = JobRepository.complete

    def inject_failure(self, *args, **kwargs):
        raise OSError("simulated storage failure")

    monkeypatch.setattr(JobRepository, "complete", inject_failure)
    with pytest.raises(OSError, match="simulated storage"):
        service.run_once()
    monkeypatch.setattr(JobRepository, "complete", original_complete)
    with closing(open_product_db(database)) as db:
        jobs = JobRepository(db)
        assert jobs.get(pending.job_id).status == "processing"
        assert jobs.get(pending.job_id).result_revision_id is None
        assert db.execute("SELECT COUNT(*) FROM transcript_revisions").fetchone()[0] == 0
        assert jobs.recover_expired(now=10**11) == 1
    assert service.run_once().status == "completed"
    assert sources.verify_blob(source.content_sha256) == len(AUDIO)


def test_cli_metadata_and_explicit_export_never_expose_transcript_implicitly(
    local, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    database, sources, transcripts, _, service, source, _ = local
    completed = service.enqueue(source.source_id)
    service.run_once()
    prefix = [
        "--database", str(database), "--blob-root", str(sources.root),
        "--transcript-root", str(transcripts.root),
    ]
    assert jobs_cli([*prefix, "status", completed.job_id]) == 0
    visible = capsys.readouterr().out
    assert "你好" not in visible
    assert json.loads(visible)["status"] == "completed"
    destination = tmp_path / "transcript-export.txt"
    assert jobs_cli([*prefix, "export-transcript", completed.job_id, str(destination)]) == 0
    response = capsys.readouterr().out
    assert json.loads(response)["exported"]
    assert destination.read_text() == "你好,新的想法。🙂\n"
    assert jobs_cli([*prefix, "export-transcript", completed.job_id, str(destination)]) == 2
    assert "INVALID_OPERATION" in capsys.readouterr().err


def test_local_model_adapter_requires_existing_directory_and_no_network(
    tmp_path: Path,
) -> None:
    with pytest.raises(TranscriptionFailure, match="local model"):
        LocalMLXWhisper(tmp_path / "nonexistent-remote-model")
    folder = tmp_path / "cached-model"
    folder.mkdir()
    a = LocalMLXWhisper(folder, language="zh")
    b = LocalMLXWhisper(folder, language="zh")
    assert a.model_key == b.model_key
    assert a.engine == "mlx-whisper"


def test_same_source_can_be_queued_for_distinct_model_versions(local) -> None:
    db, src, trans, _, service, source, _ = local

    class OtherModel(FakeLocalModel):
        model_key = "c" * 64

    first = service.enqueue(source.source_id)
    other = TranscriptionService(db, src, trans, OtherModel())
    second = other.enqueue(source.source_id)
    assert first.job_id != second.job_id
    assert service.run_once().status == "completed"
    assert other.run_once().status == "completed"
    with closing(open_product_db(db)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM transcript_revisions").fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM jobs WHERE status=\'completed\'"
        ).fetchone()[0] == 2
