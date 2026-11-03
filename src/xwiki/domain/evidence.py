"""Evidence pointers use byte offsets in a specific UTF-8 transcript revision."""

import hashlib
from dataclasses import dataclass

from .enums import ClaimModality, ClaimOwner, Confidence
from .errors import ContractError, EvidenceError
from .validation import (
    digest,
    enum_value,
    identifier,
    optional_duration,
    optional_identifier,
    refs,
    required_text,
)


@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    span_id: str
    source_id: str
    source_revision_sha256: str
    start_offset: int
    end_offset: int
    quote_sha256: str
    transcript_revision_id: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None

    def __post_init__(self) -> None:
        identifier(self.span_id, "span_id")
        identifier(self.source_id, "source_id")
        digest(self.source_revision_sha256, "source_revision_sha256")
        digest(self.quote_sha256, "quote_sha256")
        optional_identifier(self.transcript_revision_id, "transcript_revision_id")
        if (
            type(self.start_offset) is not int
            or type(self.end_offset) is not int
            or self.start_offset < 0
            or self.end_offset <= self.start_offset
        ):
            raise ContractError("evidence offsets must be a nonempty UTF-8 byte interval")
        optional_duration(self.start_ms, "start_ms")
        optional_duration(self.end_ms, "end_ms")
        if (
            self.start_ms is not None
            and self.end_ms is not None
            and self.end_ms <= self.start_ms
        ):
            raise ContractError("audio evidence must have positive duration")

    def verify_text(self, source_text: str) -> str:
        """Verify content/version SHA, Unicode boundaries and exact quoted bytes.

        This proves byte-level provenance only, NOT that a claim is semantically
        supported; independent grounding evaluation is needed in UX-003.
        """
        if not isinstance(source_text, str):
            raise EvidenceError("source text must be Unicode text")
        payload = source_text.encode("utf-8")
        if hashlib.sha256(payload).hexdigest() != self.source_revision_sha256:
            raise EvidenceError("evidence source version does not match")
        if self.end_offset > len(payload):
            raise EvidenceError("evidence end offset exceeds source length")
        try:
            quote = payload[self.start_offset : self.end_offset].decode("utf-8")
        except UnicodeDecodeError as error:
            raise EvidenceError("evidence offsets split a UTF-8 character") from error
        if hashlib.sha256(quote.encode("utf-8")).hexdigest() != self.quote_sha256:
            raise EvidenceError("evidence quoted bytes do not match")
        return quote


@dataclass(frozen=True, slots=True)
class Claim:
    claim_id: str
    text: str
    owner: ClaimOwner
    modality: ClaimModality
    confidence_bucket: Confidence
    supporting_span_ids: tuple[str, ...] = ()
    opposing_span_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        identifier(self.claim_id, "claim_id")
        required_text(self.text, "text")
        enum_value(self.owner, ClaimOwner, "owner")
        enum_value(self.modality, ClaimModality, "modality")
        enum_value(self.confidence_bucket, Confidence, "confidence_bucket")
        refs(self.supporting_span_ids, "supporting_span_ids")
        refs(self.opposing_span_ids, "opposing_span_ids")
        if not self.supporting_span_ids and not self.opposing_span_ids:
            raise ContractError("a source-backed claim requires evidence references")
