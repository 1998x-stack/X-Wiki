"""Immutable source metadata. The private file path is NOT part of the wire entity."""

from dataclasses import dataclass

from .enums import PrivacyScope, SourceOrigin, SourceStatus
from .errors import ContractError
from .validation import (
    digest,
    enum_value,
    identifier,
    optional_duration,
    optional_identifier,
    optional_text,
    timestamp,
)


@dataclass(frozen=True, slots=True)
class Source:
    source_id: str
    origin: SourceOrigin
    content_sha256: str
    created_at: str
    imported_at: str
    status: SourceStatus = SourceStatus.QUEUED
    privacy_scope: PrivacyScope = PrivacyScope.PRIVATE
    captured_at: str | None = None
    transcript_revision_id: str | None = None
    language: str | None = None
    audio_duration_ms: int | None = None

    def __post_init__(self) -> None:
        identifier(self.source_id, "source_id")
        enum_value(self.origin, SourceOrigin, "origin")
        digest(self.content_sha256, "content_sha256")
        timestamp(self.created_at, "created_at")
        timestamp(self.imported_at, "imported_at")
        enum_value(self.status, SourceStatus, "status")
        if self.privacy_scope is not PrivacyScope.PRIVATE:
            raise ContractError("source evidence must remain private")
        if self.captured_at is not None:
            timestamp(self.captured_at, "captured_at")
        optional_identifier(self.transcript_revision_id, "transcript_revision_id")
        optional_text(self.language, "language")
        optional_duration(self.audio_duration_ms, "audio_duration_ms")


@dataclass(frozen=True, slots=True)
class TranscriptRevision:
    revision_id: str
    source_id: str
    text_sha256: str
    engine: str
    model: str
    created_at: str

    def __post_init__(self) -> None:
        identifier(self.revision_id, "revision_id")
        identifier(self.source_id, "source_id")
        digest(self.text_sha256, "text_sha256")
        optional_text(self.engine, "engine")
        optional_text(self.model, "model")
        timestamp(self.created_at, "created_at")
        if not self.engine or not self.model:
            raise ContractError("transcription engine and model are required")
