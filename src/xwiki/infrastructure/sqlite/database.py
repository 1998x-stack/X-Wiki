"""Private SQLite connection and atomic, checksum-verified schema migrations.

This is deliberately a DIFFERENT database from the legacy ingest.sqlite.
Never run these migrations over the existing recordings table.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

SCHEMA_VERSION = 4
_MIGRATION_NAME = re.compile(r"^(\d{4})_[a-z][a-z0-9_]*\.sql$")


class MigrationError(RuntimeError):
    """An upgrade cannot be safely continued without administrator review."""


class ConflictError(RuntimeError):
    """An immutable entity ID already exists with different content."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    content: str
    sha256: str


def _scripts() -> list[Migration]:
    root = files("xwiki.infrastructure.sqlite.migrations")
    result: list[Migration] = []
    for script in root.iterdir():
        if not script.name.endswith(".sql"):
            continue
        found = _MIGRATION_NAME.fullmatch(script.name)
        if found is None:
            raise MigrationError(f"unexpected SQL migration filename: {script.name}")
        body = script.read_text(encoding="utf-8")
        result.append(
            Migration(int(found.group(1)), script.name, body, hashlib.sha256(
                body.encode("utf-8")
            ).hexdigest())
        )
    result.sort(key=lambda item: item.version)
    if [item.version for item in result] != list(range(1, SCHEMA_VERSION + 1)):
        raise MigrationError("missing, duplicate or unexpected schema migration")
    return result


def _statements(sql: str) -> list[str]:
    """Do not use executescript(): it auto-commits before the script runs."""
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer)
            buffer = ""
    if buffer.strip():
        raise MigrationError("SQL migration contains an incomplete statement")
    return statements


def migrate(connection: sqlite3.Connection) -> tuple[int, ...]:
    """Apply every missing migration in its own durable, rollback-safe transaction."""
    scripts = _scripts()
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY NOT NULL,
                name TEXT NOT NULL UNIQUE,
                sha256 TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise

    applied: list[int] = []
    for script in scripts:
        connection.execute("BEGIN IMMEDIATE")
        try:
            rows = connection.execute(
                "SELECT version, name, sha256 FROM schema_migrations ORDER BY version"
            ).fetchall()
            known = {row["version"]: row for row in rows}
            if any(version > SCHEMA_VERSION for version in known):
                raise MigrationError("database was created with a newer product schema")
            if script.version in known:
                existing = known[script.version]
                if existing["name"] != script.name or existing["sha256"] != script.sha256:
                    raise MigrationError(
                        f"schema migration #{script.version} has changed; refusing to continue"
                    )
                connection.execute("COMMIT")
                continue

            for statement in _statements(script.content):
                connection.execute(statement)
            connection.execute(
                """
                INSERT INTO schema_migrations(version, name, sha256, applied_at)
                VALUES(?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                """,
                (script.version, script.name, script.sha256),
            )
            connection.execute("COMMIT")
            applied.append(script.version)
        except Exception:
            connection.execute("ROLLBACK")
            raise
    # Detect unknown versions, missing entries and tampered old migrations even
    # when no migrations are pending.
    records = connection.execute(
        "SELECT version, name, sha256 FROM schema_migrations ORDER BY version"
    ).fetchall()
    if [(x["version"], x["name"], x["sha256"]) for x in records] != [
        (x.version, x.name, x.sha256) for x in scripts
    ]:
        raise MigrationError("schema migration history is incomplete or unrecognized")
    return tuple(applied)


def open_product_db(path: Path) -> sqlite3.Connection:
    """Open an owner-private product database, never an old ingestion database.

    The caller owns and must close the returned connection. SQL migrations are
    bundled in the wheel and executed transactionally.
    """
    path = Path(path).expanduser().absolute()
    if path.is_symlink() or path.parent.is_symlink():
        raise MigrationError("product database path or parent must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    connection = sqlite3.connect(path, timeout=30.0, isolation_level=None)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA foreign_keys=ON")

        # MUST happen before PRAGMA journal_mode, chmod, or schema writes:
        # accidentally passing ingest.sqlite must not mutate legacy bytes.
        legacy = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='recordings'"
        ).fetchone()
        if legacy is not None:
            raise MigrationError(
                "refusing to modify legacy recordings database; use a separate product.sqlite"
            )
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        os.chmod(path, 0o600)
        migrate(connection)
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise MigrationError("existing database violates foreign-key constraints")
        return connection
    except Exception:
        connection.close()
        raise
