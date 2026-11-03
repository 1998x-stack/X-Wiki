"""Explicit local-only transcription job queue CLI (no automatic model download).

Requires an already-installed local mlx-whisper model directory. There is no
HTTP server, pi invocation, remote provider or public Wiki publication here.
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import closing
from pathlib import Path

from xwiki.application.transcription_service import TranscriptionService
from xwiki.domain.errors import ContractError
from xwiki.infrastructure.file_store import BlobError, PrivateBlobStore
from xwiki.infrastructure.sqlite.database import ConflictError, open_product_db
from xwiki.infrastructure.sqlite.repositories import ProductRepository
from xwiki.infrastructure.whisper_adapter import LocalMLXWhisper, TranscriptionFailure


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="X-Wiki durable local transcription jobs")
    cli.add_argument("--database", type=Path, default=Path(".state/product.sqlite"))
    cli.add_argument("--blob-root", type=Path, default=Path(".state/source-store"))
    cli.add_argument("--transcript-root", type=Path, default=Path(".state/transcript-store"))
    actions = cli.add_subparsers(dest="action", required=True)
    for action in ("enqueue", "run-once"):
        entry = actions.add_parser(action)
        entry.add_argument("--model-dir", type=Path, required=True)
        entry.add_argument("--language", default="auto")
        if action == "enqueue":
            entry.add_argument("source_id")
            entry.add_argument("--max-attempts", type=int, default=3)
    for action in ("status", "retry", "cancel"):
        actions.add_parser(action).add_argument("job_id")
    actions.add_parser("recover")
    export = actions.add_parser("export-transcript")
    export.add_argument("job_id")
    export.add_argument("destination", type=Path)
    return cli


def _print(record: dict[str, object]) -> None:
    print(json.dumps(record, sort_keys=True, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.action in {"enqueue", "run-once"}:
            model = LocalMLXWhisper(args.model_dir, language=args.language)
        else:
            # Non-model commands never import MLX, download files or start inference.
            class NoModel:
                engine = "unused"
                model_key = "0" * 64

                def transcribe(self, _path: Path) -> str:
                    raise AssertionError("model must not be used by a metadata command")
            model = NoModel()

        service = TranscriptionService(
            args.database,
            PrivateBlobStore(args.blob_root),
            PrivateBlobStore(args.transcript_root),
            model,
        )
        if args.action == "enqueue":
            job = service.enqueue(args.source_id, max_attempts=args.max_attempts)
            _print({"job_id": job.job_id, "status": job.status,
                    "attempt_count": job.attempt_count})
        elif args.action == "run-once":
            outcome = service.run_once()
            _print(
                {"processed": outcome is not None}
                if outcome is None
                else {"processed": True, "job_id": outcome.job_id,
                      "status": outcome.status, "error_code": outcome.error_code,
                      "revision_id": outcome.revision_id}
            )
            if outcome is not None and outcome.status != "completed":
                return 75 if outcome.status == "failed_retryable" else 2
        elif args.action == "recover":
            _print({"recovered_jobs": service.recover()})
        elif args.action == "export-transcript":
            job = service.get(args.job_id)
            if job is None or job.status != "completed" or job.result_revision_id is None:
                raise ContractError("no completed transcript exists for this job")
            with closing(open_product_db(args.database)) as connection:
                revision = ProductRepository(connection).get_transcript_revision(
                    job.result_revision_id
                )
            if revision is None:
                raise BlobError("stored transcript metadata is missing")
            size = service.transcripts.export_original(
                revision.text_sha256, args.destination
            )
            _print({"job_id": job.job_id, "exported": True, "size_bytes": size})
        else:
            job = (
                service.get(args.job_id) if args.action == "status"
                else service.retry(args.job_id) if args.action == "retry"
                else service.cancel(args.job_id)
            )
            if job is None:
                raise ContractError("job not found")
            _print({"job_id": job.job_id, "status": job.status,
                    "attempt_count": job.attempt_count,
                    "max_attempts": job.max_attempts, "error_code": job.error_code,
                    "result_revision_id": job.result_revision_id})
        return 0
    except (ContractError, ConflictError, TranscriptionFailure, OSError, ValueError) as error:
        # Do not print arbitrary exception messages: they may include local
        # private file paths or snippets of user speech.
        label = (
            "INVALID_OPERATION" if isinstance(error, (ContractError, ValueError))
            else "LOCAL_PROCESSING_UNAVAILABLE"
        )
        print(json.dumps({"error_code": label}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
