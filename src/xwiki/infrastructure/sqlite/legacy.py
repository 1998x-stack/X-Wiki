"""Read-only, lossless snapshot import from the legacy Voice Memos SQLite store.

No UPDATE/DDL ever runs on ingest.sqlite. Legacy private paths and error strings
are retained only inside this new, gitignored product database, never exported
as Source objects or reported by the CLI.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from xwiki.domain.enums import SourceOrigin, SourceStatus
from xwiki.domain.source import Source

from .repositories import ProductRepository

LEGACY_COLUMNS = (
    "recording_id",
    "audio_sha256",
    "audio_path",
    "raw_path",
    "transcript_path",
    "model",
    "status",
    "last_error",
    "updated_at",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LEGACY_STATES = frozenset({"raw_ready", "compiled", "publish_pending", "failed"})


class LegacyImportError(RuntimeError):
    """The specified legacy database is missing, unsafe or structurally incompatible."""


@dataclass(frozen=True)
class LegacyImportReport:
    scanned: int
    added_snapshots: int
    created_sources: int
    flagged_rows: int
    unchanged_snapshots: int


def _read_legacy(path: Path) -> list[dict[str, object]]:
    path = Path(path).expanduser().absolute()
    if path.is_symlink() or not path.is_file():
        raise LegacyImportError("legacy database is missing or a symlink")
    # mode=ro reads the live WAL view without modifying the legacy SQL schema.
    legacy = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=30.0)
    try:
        legacy.row_factory = sqlite3.Row
        legacy.execute("PRAGMA busy_timeout=30000")
        actual = {row["name"] for row in legacy.execute("PRAGMA table_info(recordings)")}
        if not set(LEGACY_COLUMNS).issubset(actual):
            raise LegacyImportError("legacy recordings schema is missing required columns")
        legacy.execute("BEGIN")
        try:
            rows = legacy.execute(
                "SELECT " + ", ".join(LEGACY_COLUMNS) + " FROM recordings "
                "ORDER BY recording_id"
            ).fetchall()
            legacy.execute("COMMIT")
        except Exception:
            legacy.execute("ROLLBACK")
            raise
        return [dict(row) for row in rows]
    finally:
        legacy.close()


def _snapshot_sha(record: dict[str, object]) -> str:
    serialized = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def import_legacy_recordings(
    connection: sqlite3.Connection,
    legacy_path: Path,
    *,
    now: str | None = None,
    on_snapshot: Callable[[int], None] | None = None,
) -> LegacyImportReport:
    """Atomically append legacy snapshots and valid Source placeholders.

    Every legacy row remains represented even if its SHA is invalid. A Source
    created by migration has 'queued' status rather than falsely claiming its
    original file has been copied/verified. A source from a legacy failure is
    'failed_retryable'. File verification and actual blob copies belong to
    UX-002. A callback is available for deterministic fault-injection tests.
    """
    rows = _read_legacy(legacy_path)
    now = now or datetime.now(timezone.utc).isoformat()
    product = ProductRepository(connection)
    scanned = len(rows)
    added = created = flagged = unchanged = 0
    if connection.in_transaction:
        raise LegacyImportError("import requires a connection without an active transaction")
    connection.execute("BEGIN IMMEDIATE")
    try:
        for index, record in enumerate(rows):
            rec_id = str(record["recording_id"])
            fingerprint = _snapshot_sha(record)
            exists = connection.execute(
                "SELECT 1 FROM legacy_recording_snapshots "
                "WHERE recording_id=? AND snapshot_sha256=?",
                (rec_id, fingerprint),
            ).fetchone()
            if exists is not None:
                unchanged += 1
                continue

            audio_hash = record["audio_sha256"]
            issues: list[str] = []
            source_id: str | None = None
            if not isinstance(audio_hash, str) or not _SHA256.fullmatch(audio_hash):
                issues.append("invalid_audio_sha256")
            else:
                source_id = "legacy-" + hashlib.sha256(
                    (rec_id + "\0" + audio_hash).encode("utf-8")
                ).hexdigest()[:32]
                if record["status"] not in _LEGACY_STATES:
                    issues.append("unknown_legacy_status")
                if product.get_source(source_id) is None:
                    product.save_source(
                        Source(
                            source_id=source_id,
                            origin=SourceOrigin.VOICE_MEMO,
                            content_sha256=audio_hash,
                            created_at=now,
                            imported_at=now,
                            status=(
                                SourceStatus.FAILED_RETRYABLE
                                if record["status"] in {"failed"} or issues
                                else SourceStatus.QUEUED
                            ),
                        )
                    )
                    created += 1

            connection.execute(
                """
                INSERT INTO legacy_recording_snapshots (
                    recording_id, snapshot_sha256, audio_sha256, audio_path,
                    raw_path, transcript_path, model, status, last_error,
                    updated_at, imported_at, source_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec_id,
                    fingerprint,
                    record["audio_sha256"],
                    record["audio_path"],
                    record["raw_path"],
                    record["transcript_path"],
                    record["model"],
                    record["status"],
                    record["last_error"],
                    record["updated_at"],
                    now,
                    source_id,
                ),
            )
            connection.executemany(
                "INSERT INTO legacy_migration_issues"
                "(recording_id, snapshot_sha256, issue_code) VALUES (?, ?, ?)",
                [(rec_id, fingerprint, issue) for issue in issues],
            )
            added += 1
            if issues:
                flagged += 1
            if on_snapshot is not None:
                on_snapshot(index)
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    return LegacyImportReport(scanned, added, created, flagged, unchanged)
