"""UX-002A: store real bytes safely before declaring a source successfully stored."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from xwiki.domain.blob import BlobReceipt
from xwiki.domain.contracts import SourceStore
from xwiki.domain.enums import SourceOrigin, SourceStatus
from xwiki.domain.errors import ContractError
from xwiki.domain.source import Source


@dataclass(frozen=True, slots=True)
class ImportOutcome:
    source: Source
    blob: BlobReceipt
    duplicate: bool


class BlobPort(Protocol):
    """Minimal storage port, implemented by an owner-private local adapter."""

    def put_file(self, path: Path) -> BlobReceipt: ...

    def verify_blob(self, digest: str) -> int: ...


class ImportSource:
    def __init__(self, repository: SourceStore, blobs: BlobPort):
        self.repository = repository
        self.blobs = blobs

    def execute(
        self, path: Path, *, origin: SourceOrigin = SourceOrigin.FILE
    ) -> ImportOutcome:
        if origin not in {
            SourceOrigin.FILE,
            SourceOrigin.VOICE_MEMO,
            SourceOrigin.MARKDOWN_VAULT,
            SourceOrigin.MANUAL,
        }:
            raise ContractError("unsupported source origin")
        # The bytes are durably copied/verified BEFORE a 'stored' row exists.
        receipt = self.blobs.put_file(path)
        source_id = "source-" + hashlib.sha256(
            (origin.value + "\0" + receipt.content_sha256).encode("utf-8")
        ).hexdigest()[:32]
        existing = self.repository.get_source(source_id)
        if existing is not None:
            if existing.content_sha256 != receipt.content_sha256:
                raise ContractError("source ID is already bound to different bytes")
            self.blobs.verify_blob(existing.content_sha256)
            return ImportOutcome(existing, receipt, True)
        now = datetime.now(timezone.utc).isoformat()
        source = Source(
            source_id=source_id,
            origin=origin,
            content_sha256=receipt.content_sha256,
            created_at=now,
            imported_at=now,
            status=SourceStatus.STORED,
        )
        self.repository.save_source(source)
        return ImportOutcome(source, receipt, False)
