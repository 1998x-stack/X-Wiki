"""Pure proposed knowledge transitions; does not write approved Wiki pages."""

from dataclasses import dataclass, replace

from .enums import Confidence, ProposalKind, ProposalStatus, ReviewDecision
from .errors import ContractError, TransitionError
from .validation import (
    enum_value,
    identifier,
    optional_identifier,
    optional_text,
    refs,
    required_text,
    timestamp,
)

TRANSITIONS: dict[ProposalStatus, frozenset[ProposalStatus]] = {
    ProposalStatus.DRAFT: frozenset(
        {ProposalStatus.PROPOSED, ProposalStatus.NEEDS_EVIDENCE, ProposalStatus.FAILED}
    ),
    ProposalStatus.PROPOSED: frozenset(
        {
            ProposalStatus.APPROVED,
            ProposalStatus.REJECTED,
            ProposalStatus.NEEDS_EVIDENCE,
            ProposalStatus.SUPERSEDED,
            ProposalStatus.FAILED,
        }
    ),
    ProposalStatus.NEEDS_EVIDENCE: frozenset(
        {
            ProposalStatus.PROPOSED,
            ProposalStatus.REJECTED,
            ProposalStatus.SUPERSEDED,
            ProposalStatus.FAILED,
        }
    ),
    ProposalStatus.APPROVED: frozenset(),
    ProposalStatus.REJECTED: frozenset(),
    ProposalStatus.SUPERSEDED: frozenset(),
    ProposalStatus.FAILED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class GeneratorInfo:
    provider: str
    model: str
    version: str
    prompt_digest: str | None = None

    def __post_init__(self) -> None:
        required_text(self.provider, "generator.provider")
        required_text(self.model, "generator.model")
        required_text(self.version, "generator.version")
        optional_text(self.prompt_digest, "generator.prompt_digest")


@dataclass(frozen=True, slots=True)
class ChangeProposal:
    proposal_id: str
    node_id: str
    candidate_kind: ProposalKind
    status: ProposalStatus
    created_at: str
    before_text: str
    after_text: str
    rationale: str
    evidence_span_ids: tuple[str, ...]
    confidence_bucket: Confidence
    base_revision_id: str | None = None
    uncertainty_notes: tuple[str, ...] = ()
    generator: GeneratorInfo | None = None
    external_processing_approved: bool = False

    def __post_init__(self) -> None:
        identifier(self.proposal_id, "proposal_id")
        identifier(self.node_id, "node_id")
        enum_value(self.candidate_kind, ProposalKind, "candidate_kind")
        enum_value(self.status, ProposalStatus, "status")
        timestamp(self.created_at, "created_at")
        if not isinstance(self.before_text, str) or not isinstance(self.after_text, str):
            raise ContractError("before_text and after_text must be strings")
        required_text(self.rationale, "rationale")
        refs(self.evidence_span_ids, "evidence_span_ids")
        enum_value(self.confidence_bucket, Confidence, "confidence_bucket")
        optional_identifier(self.base_revision_id, "base_revision_id")
        if not isinstance(self.uncertainty_notes, tuple):
            raise ContractError("uncertainty_notes must be a tuple")
        for note in self.uncertainty_notes:
            required_text(note, "uncertainty_notes")
        if self.generator is not None and not isinstance(self.generator, GeneratorInfo):
            raise ContractError("generator must be GeneratorInfo or null")
        if type(self.external_processing_approved) is not bool:
            raise ContractError("external_processing_approved must be boolean")
        if self.candidate_kind is ProposalKind.NEW:
            if self.base_revision_id is not None or self.before_text:
                raise ContractError("new nodes must not have an existing base or before_text")
            required_text(self.after_text, "after_text")
        elif self.candidate_kind not in {ProposalKind.NO_CHANGE, ProposalKind.UNCERTAIN}:
            if self.base_revision_id is None:
                raise ContractError("knowledge edits require base_revision_id for CAS")
            required_text(self.before_text, "before_text")
            required_text(self.after_text, "after_text")
        if self.candidate_kind is ProposalKind.NO_CHANGE:
            if self.status is ProposalStatus.APPROVED:
                raise ContractError("no_change cannot be approved as a revision")
            if self.before_text != self.after_text:
                raise ContractError("no_change cannot modify knowledge text")
        if self.status is ProposalStatus.APPROVED and not self.evidence_span_ids:
            raise ContractError("approved proposals must reference evidence")

    def transition(self, target: ProposalStatus) -> "ChangeProposal":
        """Domain-only transition; not an authorization or evidence grounding check."""
        enum_value(target, ProposalStatus, "target")
        if target not in TRANSITIONS[self.status]:
            raise TransitionError(f"invalid proposal transition: {self.status.value} → {target.value}")
        if target is ProposalStatus.APPROVED:
            if self.candidate_kind in {ProposalKind.NO_CHANGE, ProposalKind.UNCERTAIN}:
                raise TransitionError("no_change/uncertain cannot become approved revisions")
            if not self.evidence_span_ids:
                raise TransitionError("approval requires evidence references")
        return replace(self, status=target)


@dataclass(frozen=True, slots=True)
class ReviewAction:
    action_id: str
    proposal_id: str
    reviewer_id: str
    decision: ReviewDecision
    reviewed_at: str
    idempotency_key: str

    def __post_init__(self) -> None:
        identifier(self.action_id, "action_id")
        identifier(self.proposal_id, "proposal_id")
        identifier(self.reviewer_id, "reviewer_id")
        enum_value(self.decision, ReviewDecision, "decision")
        timestamp(self.reviewed_at, "reviewed_at")
        identifier(self.idempotency_key, "idempotency_key")
