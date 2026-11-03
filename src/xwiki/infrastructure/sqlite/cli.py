"""CLI for owner-private product schema upgrades and explicit legacy import.

No invocation performs transcription, model inference, Git push or Pages export.
"""

from __future__ import annotations

import argparse
import json
from contextlib import closing
import re
from pathlib import Path

from .database import SCHEMA_VERSION, open_product_db
from .legacy import _read_legacy, import_legacy_recordings

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KNOWN = {"raw_ready", "compiled", "publish_pending", "failed"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and migrate local X-Wiki product state")
    parser.add_argument("--database", type=Path, default=Path(".state/product.sqlite"))
    parser.add_argument("--legacy", type=Path, default=Path(".state/ingest.sqlite"))
    parser.add_argument(
        "--import-legacy",
        action="store_true",
        help="read the legacy recordings DB and append versioned private snapshots",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="inspect legacy data without creating or modifying a database",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.dry_run and not args.import_legacy:
        raise SystemExit("--dry-run requires --import-legacy")
    if args.dry_run:
        rows = _read_legacy(args.legacy)
        print(
            json.dumps(
                {
                    "mode": "read_only",
                    "recordings": len(rows),
                    "invalid_hashes": sum(
                        not isinstance(row["audio_sha256"], str)
                        or not _SHA256.fullmatch(row["audio_sha256"])
                        for row in rows
                    ),
                    "unknown_statuses": sum(row["status"] not in _KNOWN for row in rows),
                },
                sort_keys=True,
            )
        )
        return 0

    with closing(open_product_db(args.database)) as connection:
        result: dict[str, object] = {"schema_version": SCHEMA_VERSION}
        if args.import_legacy:
            report = import_legacy_recordings(connection, args.legacy)
            result["legacy_import"] = {
                "scanned": report.scanned,
                "added_snapshots": report.added_snapshots,
                "created_sources": report.created_sources,
                "flagged_rows": report.flagged_rows,
                "unchanged_snapshots": report.unchanged_snapshots,
            }
        result["sources"] = connection.execute("SELECT count(*) FROM sources").fetchone()[0]
        result["snapshot_rows"] = connection.execute(
            "SELECT count(*) FROM legacy_recording_snapshots"
        ).fetchone()[0]
        result["integrity"] = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if result["integrity"] != "ok":
            raise RuntimeError("product SQLite integrity check failed")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
