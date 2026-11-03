"""Local-only, explicit import/verify/export CLI for real user-owned files.

This CLI does not invoke Whisper, LLM providers, Git or public publication.
It reports only safe IDs, hashes, byte sizes and state; no private paths.
"""

from __future__ import annotations

import argparse
import json
from contextlib import closing
from pathlib import Path

from xwiki.application.import_source import ImportSource
from xwiki.domain.enums import SourceOrigin
from xwiki.infrastructure.file_store import PrivateBlobStore
from xwiki.infrastructure.sqlite.database import open_product_db
from xwiki.infrastructure.sqlite.repositories import ProductRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="X-Wiki local source storage")
    parser.add_argument("--database", type=Path, default=Path(".state/product.sqlite"))
    parser.add_argument("--blob-root", type=Path, default=Path(".state/source-store"))
    group = parser.add_subparsers(dest="action", required=True)
    add = group.add_parser("import", help="durably save a TXT/MD/M4A/MP3/WAV file")
    add.add_argument("file", type=Path)
    add.add_argument(
        "--origin",
        choices=[item.value for item in SourceOrigin],
        default=SourceOrigin.FILE.value,
    )
    verify = group.add_parser("verify", help="verify stored source digest and file size")
    verify.add_argument("source_id")
    export = group.add_parser("export", help="export verified bytes to a NEW file path")
    export.add_argument("source_id")
    export.add_argument("destination", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    with closing(open_product_db(args.database)) as connection:
        repo = ProductRepository(connection)
        store = PrivateBlobStore(args.blob_root)
        if args.action == "import":
            result = ImportSource(repo, store).execute(
                args.file, origin=SourceOrigin(args.origin)
            )
            print(
                json.dumps(
                    {
                        "source_id": result.source.source_id,
                        "content_sha256": result.source.content_sha256,
                        "status": result.source.status.value,
                        "size_bytes": result.blob.size_bytes,
                        "media_kind": result.blob.media_kind,
                        "duplicate": result.duplicate,
                    },
                    sort_keys=True,
                )
            )
        else:
            source = repo.get_source(args.source_id)
            if source is None:
                raise ValueError("source not found in private product store")
            if args.action == "verify":
                size = store.verify_blob(source.content_sha256)
                print(json.dumps({"source_id": source.source_id, "verified": True,
                                  "size_bytes": size}, sort_keys=True))
            else:
                size = store.export_original(source.content_sha256, args.destination)
                print(json.dumps({"source_id": source.source_id, "exported": True,
                                  "size_bytes": size}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
