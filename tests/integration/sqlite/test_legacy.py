"""Legacy read-only import, WAL consistency and crash rollback acceptance tests."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from xwiki.domain.enums import SourceStatus
from xwiki.infrastructure.sqlite.cli import main
from xwiki.infrastructure.sqlite.database import open_product_db
from xwiki.infrastructure.sqlite.legacy import LegacyImportError, import_legacy_recordings
from xwiki.infrastructure.sqlite.repositories import ProductRepository

STAMP = "2026-11-03T00:00:00+00:00"
HASH = hashlib.sha256(b"old audio").hexdigest()


def create_legacy(path: Path, *, wal: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE recordings (
            recording_id TEXT PRIMARY KEY,
            audio_sha256 TEXT NOT NULL,
            audio_path TEXT NOT NULL,
            raw_path TEXT,
            transcript_path TEXT,
            model TEXT NOT NULL,
            status TEXT NOT NULL,
            last_error TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def add(
    conn: sqlite3.Connection,
    recording_id: str,
    *,
    audio_sha: str = HASH,
    status: str = "raw_ready",
    error: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO recordings VALUES (?,?,?,?,?,?,?,?,?)",
        (recording_id, audio_sha, "/private/recording-" + recording_id + ".m4a",
         "/private/raw-" + recording_id + ".md",
         "/private/transcript-" + recording_id + ".json",
         "whisper|zh|no-context", status, error, STAMP),
    )
    conn.commit()


def test_read_only_snapshot_preserves_legacy_bytes_and_paths_private(tmp_path: Path) -> None:
    legacy = tmp_path / "ingest.sqlite"
    with create_legacy(legacy) as writer:
        add(writer, "voice-01", status="compiled", error="legacy error content")
    before = hashlib.sha256(legacy.read_bytes()).hexdigest()
    with open_product_db(tmp_path / "product.sqlite") as product:
        result = import_legacy_recordings(product, legacy, now=STAMP)
        assert result.scanned == 1
        assert result.added_snapshots == 1
        assert result.created_sources == 1
        assert result.flagged_rows == 0
        snapshot = product.execute(
            "SELECT * FROM legacy_recording_snapshots"
        ).fetchone()
        assert snapshot["audio_sha256"] == HASH
        assert snapshot["status"] == "compiled"
        assert snapshot["audio_path"] == "/private/recording-voice-01.m4a"
        assert snapshot["last_error"] == "legacy error content"
        source = ProductRepository(product).get_source(snapshot["source_id"])
        assert source is not None
        assert source.content_sha256 == HASH
        assert source.status is SourceStatus.QUEUED
        assert not any("path" in field for field in source.__dataclass_fields__)
    assert hashlib.sha256(legacy.read_bytes()).hexdigest() == before


def test_import_twice_is_idempotent(tmp_path: Path) -> None:
    legacy = tmp_path / "ingest.sqlite"
    with create_legacy(legacy) as writer:
        add(writer, "voice-01")
        add(writer, "voice-02")
    with open_product_db(tmp_path / "product.sqlite") as db:
        first = import_legacy_recordings(db, legacy, now=STAMP)
        second = import_legacy_recordings(db, legacy, now=STAMP)
        assert first.added_snapshots == 2
        assert first.created_sources == 2
        assert second.added_snapshots == 0
        assert second.created_sources == 0
        assert second.unchanged_snapshots == 2
        assert db.execute("SELECT count(*) FROM sources").fetchone()[0] == 2
        assert db.execute(
            "SELECT count(*) FROM legacy_recording_snapshots"
        ).fetchone()[0] == 2


def test_changed_legacy_status_appends_snapshot_without_losing_history(tmp_path: Path) -> None:
    legacy = tmp_path / "ingest.sqlite"
    with create_legacy(legacy) as writer:
        add(writer, "voice-01", status="raw_ready")
        with open_product_db(tmp_path / "product.sqlite") as db:
            import_legacy_recordings(db, legacy, now=STAMP)
            writer.execute(
                "UPDATE recordings SET status='publish_pending' WHERE recording_id='voice-01'"
            )
            writer.commit()
            second = import_legacy_recordings(db, legacy, now=STAMP)
            assert second.added_snapshots == 1
            assert second.created_sources == 0
            statuses = {
                row[0] for row in db.execute("SELECT status FROM legacy_recording_snapshots")
            }
            assert statuses == {"raw_ready", "publish_pending"}
            assert db.execute("SELECT count(*) FROM sources").fetchone()[0] == 1


def test_invalid_hash_is_retained_and_flagged_not_silently_dropped(tmp_path: Path) -> None:
    legacy = tmp_path / "ingest.sqlite"
    with create_legacy(legacy) as writer:
        add(writer, "voice-bad", audio_sha="NOT_A_SHA", status="failed")
    with open_product_db(tmp_path / "product.sqlite") as db:
        report = import_legacy_recordings(db, legacy, now=STAMP)
        assert (report.scanned, report.flagged_rows, report.created_sources) == (1, 1, 0)
        snapshot = db.execute("SELECT * FROM legacy_recording_snapshots").fetchone()
        assert snapshot["source_id"] is None
        assert snapshot["audio_sha256"] == "NOT_A_SHA"
        issue = db.execute("SELECT issue_code FROM legacy_migration_issues").fetchone()[0]
        assert issue == "invalid_audio_sha256"


def test_legacy_failure_never_claims_original_audio_is_verified(tmp_path: Path) -> None:
    legacy = tmp_path / "ingest.sqlite"
    with create_legacy(legacy) as writer:
        add(writer, "voice-01", status="failed")
    with open_product_db(tmp_path / "product.sqlite") as db:
        import_legacy_recordings(db, legacy, now=STAMP)
        source_id = db.execute("SELECT source_id FROM legacy_recording_snapshots").fetchone()[0]
        assert ProductRepository(db).get_source(source_id).status is SourceStatus.FAILED_RETRYABLE


def test_unknown_legacy_state_is_preserved_and_flagged(tmp_path: Path) -> None:
    legacy = tmp_path / "ingest.sqlite"
    with create_legacy(legacy) as writer:
        add(writer, "voice-01", status="some-new-legacy-state")
    with open_product_db(tmp_path / "product.sqlite") as db:
        report = import_legacy_recordings(db, legacy, now=STAMP)
        assert report.flagged_rows == 1
        assert db.execute("SELECT status FROM legacy_recording_snapshots").fetchone()[0] == (
            "some-new-legacy-state"
        )
        assert db.execute("SELECT issue_code FROM legacy_migration_issues").fetchone()[0] == (
            "unknown_legacy_status"
        )


def test_failed_mid_import_rolls_back_all_product_changes(tmp_path: Path) -> None:
    legacy = tmp_path / "ingest.sqlite"
    with create_legacy(legacy) as writer:
        add(writer, "voice-01")
        add(writer, "voice-02")
    with open_product_db(tmp_path / "product.sqlite") as db:
        def stop(index: int) -> None:
            if index == 1:
                raise RuntimeError("injected process interruption")

        with pytest.raises(RuntimeError, match="injected"):
            import_legacy_recordings(db, legacy, now=STAMP, on_snapshot=stop)
        assert db.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
        assert db.execute(
            "SELECT count(*) FROM legacy_recording_snapshots"
        ).fetchone()[0] == 0
        assert import_legacy_recordings(db, legacy, now=STAMP).created_sources == 2


def test_read_only_import_sees_committed_wal_records(tmp_path: Path) -> None:
    legacy = tmp_path / "ingest.sqlite"
    writer = create_legacy(legacy, wal=True)
    try:
        add(writer, "voice-in-wal")
        with open_product_db(tmp_path / "product.sqlite") as db:
            report = import_legacy_recordings(db, legacy, now=STAMP)
            assert report.scanned == 1
    finally:
        writer.close()


def test_incompatible_legacy_schema_does_not_touch_product_rows(tmp_path: Path) -> None:
    legacy = tmp_path / "ingest.sqlite"
    with sqlite3.connect(legacy) as writer:
        writer.execute("CREATE TABLE recordings (recording_id TEXT PRIMARY KEY)")
    with open_product_db(tmp_path / "product.sqlite") as db:
        with pytest.raises(LegacyImportError, match="missing required"):
            import_legacy_recordings(db, legacy, now=STAMP)
        assert db.execute(
            "SELECT count(*) FROM legacy_recording_snapshots"
        ).fetchone()[0] == 0


def test_cli_dry_run_is_read_only_and_never_prints_private_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    legacy = tmp_path / "ingest.sqlite"
    with create_legacy(legacy) as writer:
        add(writer, "voice-01", error="secret-internal-error")
    product = tmp_path / "never-created.sqlite"
    assert main(["--legacy", str(legacy), "--database", str(product),
                 "--import-legacy", "--dry-run"]) == 0
    output = capsys.readouterr().out
    data = json.loads(output)
    assert data == {
        "mode": "read_only", "recordings": 1,
        "invalid_hashes": 0, "unknown_statuses": 0,
    }
    assert "/private/" not in output
    assert "secret" not in output
    assert not product.exists()


def test_cli_import_is_explicit_and_outputs_only_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    legacy = tmp_path / "ingest.sqlite"
    with create_legacy(legacy) as writer:
        add(writer, "voice-01", error="secret")
    product = tmp_path / "product.sqlite"
    args = ["--database", str(product), "--legacy", str(legacy)]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["snapshot_rows"] == 0
    assert main([*args, "--import-legacy"]) == 0
    response = capsys.readouterr().out
    assert json.loads(response)["legacy_import"]["added_snapshots"] == 1
    assert "/private/" not in response
    assert "secret" not in response
