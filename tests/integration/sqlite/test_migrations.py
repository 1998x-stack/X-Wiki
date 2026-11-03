"""ARCH-00B: transactional migration, schema integrity and safety tests."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from xwiki.infrastructure.sqlite import database
from xwiki.infrastructure.sqlite.database import MigrationError, open_product_db


def _db(tmp_path: Path) -> Path:
    return tmp_path / ".state" / "product.sqlite"


def test_fresh_database_has_all_migrations_private_permissions_and_wal(tmp_path: Path) -> None:
    target = _db(tmp_path)
    with open_product_db(target) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert [row["version"] for row in conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        )] == [1, 2, 3, 4]
        for table in (
            "sources", "legacy_recording_snapshots", "legacy_migration_issues",
            "transcript_revisions", "evidence_spans", "claims", "claim_evidence",
            "knowledge_nodes", "knowledge_revisions", "change_proposals",
            "review_actions", "jobs", "job_attempts"
        ):
            assert conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert target.exists()
    if os.name == "posix":
        assert target.stat().st_mode & 0o077 == 0
        assert target.parent.stat().st_mode & 0o077 == 0


def test_migration_is_idempotent_even_after_reopening(tmp_path: Path) -> None:
    path = _db(tmp_path)
    with open_product_db(path) as conn:
        original = conn.execute(
            "SELECT version,name,sha256 FROM schema_migrations ORDER BY version"
        ).fetchall()
        assert database.migrate(conn) == ()
    with open_product_db(path) as conn:
        assert [tuple(row) for row in conn.execute(
            "SELECT version,name,sha256 FROM schema_migrations ORDER BY version"
        )] == [tuple(row) for row in original]
        assert database.migrate(conn) == ()


def test_legacy_database_refused_without_modification(tmp_path: Path) -> None:
    path = tmp_path / "ingest.sqlite"
    with sqlite3.connect(path) as old:
        old.execute("CREATE TABLE recordings (recording_id TEXT PRIMARY KEY)")
        old.execute("INSERT INTO recordings VALUES ('original')")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(MigrationError, match="refusing to modify legacy"):
        open_product_db(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    with sqlite3.connect(path) as old:
        assert old.execute("SELECT recording_id FROM recordings").fetchone()[0] == "original"
        assert old.execute(
            "SELECT count(*) FROM sqlite_master WHERE name='schema_migrations'"
        ).fetchone()[0] == 0


def test_rejects_symlinked_database_and_parent(tmp_path: Path) -> None:
    actual = tmp_path / "real"
    actual.mkdir()
    (actual / "original.sqlite").write_bytes(b"not a database")
    link = tmp_path / "linked.sqlite"
    link.symlink_to(actual / "original.sqlite")
    with pytest.raises(MigrationError, match="symlink"):
        open_product_db(link)
    parent_link = tmp_path / "linked-parent"
    parent_link.symlink_to(actual, target_is_directory=True)
    with pytest.raises(MigrationError, match="symlink"):
        open_product_db(parent_link / "product.sqlite")


def test_schema_checksum_drift_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _db(tmp_path)
    with open_product_db(target):
        pass
    original_scripts = database._scripts
    first, *tail = original_scripts()
    corrupted = replace(first, sha256="f" * 64)
    monkeypatch.setattr(database, "_scripts", lambda: [corrupted, *tail])
    with pytest.raises(MigrationError, match="has changed"):
        open_product_db(target)
    monkeypatch.setattr(database, "_scripts", original_scripts)
    with open_product_db(target) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_future_schema_versions_refused(tmp_path: Path) -> None:
    target = _db(tmp_path)
    with open_product_db(target) as conn:
        conn.execute(
            "INSERT INTO schema_migrations VALUES (999,'future.sql',?,?)",
            ("a" * 64, "2026-11-03T00:00:00Z"),
        )
    with pytest.raises(MigrationError, match="newer"):
        open_product_db(target)


def test_failed_migration_rolls_back_all_its_ddl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _db(tmp_path)
    originals = database._scripts()
    first = originals[0]
    interrupted = (
        "CREATE TABLE temporary_test(id INTEGER);\n"
        "CREATE TABLE temporary_test(id INTEGER);\n"
    )
    broken = replace(first, content=interrupted, sha256=hashlib.sha256(
        interrupted.encode("utf-8")
    ).hexdigest())
    monkeypatch.setattr(database, "_scripts", lambda: [broken, *originals[1:]])
    with pytest.raises(sqlite3.OperationalError, match="already exists"):
        open_product_db(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 0
        assert conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE name='temporary_test'"
        ).fetchone()[0] == 0
    monkeypatch.setattr(database, "_scripts", lambda: originals)
    with open_product_db(path) as conn:
        assert conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 4


def test_upgrade_from_version_one_preserves_old_data(tmp_path: Path) -> None:
    path = _db(tmp_path)
    path.parent.mkdir(parents=True)
    scripts = database._scripts()
    with sqlite3.connect(path, isolation_level=None) as raw:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("CREATE TABLE schema_migrations "
                    "(version INTEGER PRIMARY KEY, name TEXT, sha256 TEXT, applied_at TEXT)")
        raw.execute("BEGIN IMMEDIATE")
        for sql in database._statements(scripts[0].content):
            raw.execute(sql)
        raw.execute(
            "INSERT INTO schema_migrations VALUES (1, ?, ?, '2026-11-03T00:00:00Z')",
            (scripts[0].name, scripts[0].sha256),
        )
        raw.execute(
            "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("source-01", "file", "a" * 64, "2026-11-03T00:00:00Z",
             "2026-11-03T00:00:00Z", "queued", "private", None, None, None, None),
        )
        raw.execute("COMMIT")
    with open_product_db(path) as upgraded:
        assert upgraded.execute("SELECT count(*) FROM sources").fetchone()[0] == 1
        assert upgraded.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 4
        assert upgraded.execute("PRAGMA foreign_key_check").fetchall() == []


def test_sql_offset_and_private_checks_enforced(tmp_path: Path) -> None:
    with open_product_db(_db(tmp_path)) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sources (source_id,origin,content_sha256,created_at,"
                "imported_at,status,privacy_scope) VALUES (?,?,?,?,?,?,?)",
                ("bad", "file", "a" * 64, "2026-11-03T00:00:00Z",
                 "2026-11-03T00:00:00Z", "stored", "public"),
            )
        assert conn.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
