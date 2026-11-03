"""Independent negative-domain tests: no model, SQLite or network required."""

import hashlib
import json
from dataclasses import FrozenInstanceError, fields

import pytest

from xwiki.domain.codec import from_payload, to_payload
from xwiki.domain.enums import (
    ClaimModality,
    ClaimOwner,
    Confidence,
    DataDestination,
    KnowledgeKind,
    PrivacyScope,
    ProposalKind,
    ProposalStatus,
    ReviewDecision,
    SourceOrigin,
)
from xwiki.domain.errors import ContractError, EvidenceError, PermissionDenied, TransitionError
from xwiki.domain.evidence import Claim, EvidenceSpan
from xwiki.domain.knowledge import KnowledgeNode, KnowledgeRevision
from xwiki.domain.privacy import ProcessingConsent, can_transfer, require_transfer
from xwiki.domain.proposal import ChangeProposal, GeneratorInfo, ReviewAction
from xwiki.domain.source import Source, TranscriptRevision

NOW = "2026-11-03T09:12:00+08:00"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source() -> Source:
    return Source(
        source_id="source-01",
        origin=SourceOrigin.VOICE_MEMO,
        content_sha256=sha("audio"),
        created_at=NOW,
        imported_at=NOW,
    )


def proposal(**changes: object) -> ChangeProposal:
    values: dict[str, object] = {
        "proposal_id": "proposal-01",
        "node_id": "node-01",
        "candidate_kind": ProposalKind.QUALIFY,
        "status": ProposalStatus.PROPOSED,
        "created_at": NOW,
        "before_text": "A fixed schedule is always best.",
        "after_text": "A fixed schedule helps but sometimes flexibility is useful.",
        "rationale": "New evidence qualifies an earlier judgment.",
        "evidence_span_ids": ("span-01", "span-02"),
        "confidence_bucket": Confidence.MEDIUM,
        "base_revision_id": "revision-01",
    }
    values.update(changes)
    return ChangeProposal(**values)


@pytest.mark.parametrize(
    "model",
    [
        source(),
        TranscriptRevision("transcript-01", "source-01", sha("text"), "mlx-whisper", "base", NOW),
        KnowledgeNode("node-01", "Daily systems", KnowledgeKind.CONCEPT),
        KnowledgeRevision("revision-01", "node-01", sha("text"), NOW, "user-01", "action-01"),
        proposal(),
        ReviewAction("action-01", "proposal-01", "user-01", ReviewDecision.APPROVE, NOW, "key-01"),
        Claim("claim-01", "A new claim", ClaimOwner.SOURCE, ClaimModality.ASSERTION,
              Confidence.HIGH, supporting_span_ids=("span-01",)),
        GeneratorInfo("demo-only", "hand-authored", "1"),
    ],
)
def test_round_trip_is_strict_and_json_serializable(model: object) -> None:
    encoded = to_payload(model)
    serialized = json.loads(json.dumps(encoded))
    assert from_payload(type(model), serialized) == model
    with pytest.raises(FrozenInstanceError):
        setattr(model, fields(model)[0].name, "new-value")


def test_source_has_private_defaults_without_a_path_leak() -> None:
    item = source()
    assert item.privacy_scope is PrivacyScope.PRIVATE
    assert item.status.value == "queued"
    assert not any("path" in key for key in to_payload(item))


@pytest.mark.parametrize(
    "changes",
    [
        {"source_id": "../raw"},
        {"content_sha256": "DEADBEEF"},
        {"created_at": "2026-11-03T09:12:00"},
        {"imported_at": "not-a-date"},
        {"privacy_scope": PrivacyScope.PUBLIC},
        {"audio_duration_ms": True},
        {"audio_duration_ms": -4},
        {"origin": "voice_memo"},
    ],
)
def test_source_rejects_invalid_values(changes: dict[str, object]) -> None:
    payload = to_payload(source())
    payload.update(changes)
    # Direct construction uses enum objects; wire input uses strings.
    if "origin" not in changes:
        payload["origin"] = SourceOrigin.VOICE_MEMO
    payload["status"] = source().status
    payload["privacy_scope"] = changes.get("privacy_scope", PrivacyScope.PRIVATE)
    with pytest.raises(ContractError):
        Source(**payload)


def test_evidence_offsets_use_utf8_bytes_not_python_char_positions() -> None:
    document = "甲🙂B"
    item = EvidenceSpan(
        span_id="span-01",
        source_id="source-01",
        source_revision_sha256=sha(document),
        start_offset=3,
        end_offset=7,
        quote_sha256=sha("🙂"),
        start_ms=100,
        end_ms=140,
    )
    assert item.verify_text(document) == "🙂"
    with pytest.raises(EvidenceError, match="version"):
        item.verify_text(document + "!")
    with pytest.raises(EvidenceError, match="UTF-8"):
        EvidenceSpan("span-01", "source-01", sha(document), 4, 7, sha("🙂")).verify_text(
            document
        )
    with pytest.raises(EvidenceError, match="quoted bytes"):
        EvidenceSpan("span-01", "source-01", sha(document), 0, 3, sha("🙂")).verify_text(
            document
        )
    with pytest.raises(EvidenceError, match="exceeds"):
        EvidenceSpan("span-01", "source-01", sha(document), 3, 20, sha("🙂")).verify_text(
            document
        )


@pytest.mark.parametrize("start,end", [(1, 1), (-1, 2), (True, 2), (2, 0)])
def test_evidence_rejects_invalid_ranges(start: object, end: object) -> None:
    with pytest.raises(ContractError):
        EvidenceSpan("span-01", "source-01", sha("x"), start, end, sha("x"))


def test_claim_requires_evidence_and_no_duplicate_refs() -> None:
    with pytest.raises(ContractError, match="requires evidence"):
        Claim("claim-01", "text", ClaimOwner.USER, ClaimModality.QUESTION, Confidence.UNKNOWN)
    with pytest.raises(ContractError, match="duplicate"):
        Claim("claim-01", "text", ClaimOwner.USER, ClaimModality.QUESTION,
              Confidence.UNKNOWN, supporting_span_ids=("span-01", "span-01"))


def test_knowledge_never_becomes_public_by_construction() -> None:
    with pytest.raises(ContractError, match="private"):
        KnowledgeNode("node-01", "Topic", KnowledgeKind.CONCEPT,
                      privacy_scope=PrivacyScope.PUBLIC)
    with pytest.raises(ContractError, match="own parent"):
        KnowledgeRevision("rev-1", "node-01", sha("x"), NOW, "user", "key",
                          parent_revision_id="rev-1")


def test_proposal_transition_is_pure_and_terminal_states_cannot_reopen() -> None:
    original = proposal()
    approved = original.transition(ProposalStatus.APPROVED)
    assert original.status is ProposalStatus.PROPOSED
    assert approved.status is ProposalStatus.APPROVED
    with pytest.raises(TransitionError):
        approved.transition(ProposalStatus.PROPOSED)
    assert proposal(status=ProposalStatus.NEEDS_EVIDENCE).transition(
        ProposalStatus.PROPOSED
    ).status is ProposalStatus.PROPOSED


def test_proposal_guards_no_change_uncertainty_and_missing_evidence() -> None:
    with pytest.raises(ContractError, match="no_change"):
        proposal(candidate_kind=ProposalKind.NO_CHANGE, status=ProposalStatus.APPROVED)
    with pytest.raises(ContractError, match="no_change"):
        proposal(candidate_kind=ProposalKind.NO_CHANGE)
    with pytest.raises(TransitionError, match="requires evidence"):
        proposal(evidence_span_ids=()).transition(ProposalStatus.APPROVED)
    with pytest.raises(TransitionError, match="uncertain"):
        proposal(candidate_kind=ProposalKind.UNCERTAIN).transition(ProposalStatus.APPROVED)
    with pytest.raises(ContractError, match="base_revision_id"):
        proposal(base_revision_id=None)


def test_new_node_has_no_base_revision_and_requires_content() -> None:
    new = proposal(
        candidate_kind=ProposalKind.NEW, base_revision_id=None, before_text=""
    )
    assert new.transition(ProposalStatus.APPROVED).status is ProposalStatus.APPROVED
    with pytest.raises(ContractError):
        proposal(candidate_kind=ProposalKind.NEW, base_revision_id="rev-1")


def test_privacy_is_deny_by_default_and_publication_needs_separate_gate() -> None:
    assert can_transfer(PrivacyScope.PRIVATE, DataDestination.DEVICE)
    assert not can_transfer(PrivacyScope.PRIVATE, DataDestination.EXTERNAL_MODEL)
    assert not can_transfer(PrivacyScope.PRIVATE, DataDestination.PUBLIC_WEB)
    with pytest.raises(PermissionDenied):
        require_transfer(PrivacyScope.PRIVATE, DataDestination.EXTERNAL_MODEL)
    valid = ProcessingConsent(DataDestination.EXTERNAL_MODEL, granted=True)
    assert can_transfer(PrivacyScope.PRIVATE, DataDestination.EXTERNAL_MODEL, consent=valid)
    assert not can_transfer(PrivacyScope.PRIVATE, DataDestination.PUBLIC_WEB, consent=valid)
    with pytest.raises(ContractError):
        ProcessingConsent(DataDestination.EXTERNAL_MODEL, granted="yes")


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_id", "../outside"),
        ("audio_duration_ms", True),
        ("origin", "unknown"),
        ("privacy_scope", "public"),
        ("created_at", "2026-11-03"),
        ("captured_at", ""),
    ],
)
def test_wire_codec_rejects_invalid_source_payload(field: str, value: object) -> None:
    data = to_payload(source())
    data[field] = value
    with pytest.raises(ContractError):
        from_payload(Source, data)


def test_wire_codec_rejects_unknown_missing_and_wrong_nesting() -> None:
    original = to_payload(proposal(generator=GeneratorInfo("local", "model", "1")))
    with pytest.raises(ContractError, match="unknown fields"):
        from_payload(ChangeProposal, {**original, "debug_token": "SECRET"})
    with pytest.raises(ContractError, match="required"):
        from_payload(Source, {"source_id": "x"})
    with pytest.raises(ContractError):
        from_payload(ChangeProposal, {**original, "evidence_span_ids": "span-01"})
    with pytest.raises(ContractError):
        from_payload(ChangeProposal, {**original, "generator": {"provider": "x"}})
    with pytest.raises(ContractError):
        from_payload(ChangeProposal, {**original, "external_processing_approved": 1})


def test_generator_is_not_evidence_of_network_permission() -> None:
    item = proposal(generator=GeneratorInfo("external", "model", "1"))
    assert item.external_processing_approved is False
    assert not can_transfer(PrivacyScope.PRIVATE, DataDestination.EXTERNAL_MODEL)
