"""ARCH-00B: immutable, foreign-key-backed domain persistence contracts."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from xwiki.domain.enums import (
    ClaimModality,
    ClaimOwner,
    Confidence,
    KnowledgeKind,
    ProposalKind,
    ProposalStatus,
    ReviewDecision,
    SourceOrigin,
)
from xwiki.domain.errors import ContractError, EvidenceError
from xwiki.domain.evidence import Claim, EvidenceSpan
from xwiki.domain.knowledge import KnowledgeNode
from xwiki.domain.proposal import ChangeProposal, ReviewAction
from xwiki.domain.source import Source, TranscriptRevision
from xwiki.infrastructure.sqlite.database import ConflictError, open_product_db
from xwiki.infrastructure.sqlite.repositories import ProductRepository

NOW = "2026-11-03T16:00:00+08:00"
TEXT = "旧观点🙂新记录"
SHA = hashlib.sha256(TEXT.encode("utf-8")).hexdigest()


@pytest.fixture
def store(tmp_path: Path):
    db = open_product_db(tmp_path / ".state" / "product.sqlite")
    try:
        yield ProductRepository(db)
    finally:
        db.close()


def _source(source_id: str = "source-01") -> Source:
    return Source(
        source_id=source_id,
        origin=SourceOrigin.FILE,
        content_sha256=SHA,
        created_at=NOW,
        imported_at=NOW,
    )


def _span(span_id: str = "span-01") -> EvidenceSpan:
    return EvidenceSpan(
        span_id=span_id,
        source_id="source-01",
        source_revision_sha256=SHA,
        start_offset=0,
        end_offset=len(TEXT.encode("utf-8")),
        quote_sha256=SHA,
    )


def _proposal(*, proposal_id: str = "proposal-01") -> ChangeProposal:
    return ChangeProposal(
        proposal_id=proposal_id,
        node_id="node-01",
        candidate_kind=ProposalKind.NEW,
        status=ProposalStatus.PROPOSED,
        created_at=NOW,
        before_text="",
        after_text="One structured idea",
        rationale="A supported, initial knowledge note",
        evidence_span_ids=("span-01",),
        confidence_bucket=Confidence.MEDIUM,
    )


def test_source_roundtrip_and_idempotent_insert(store: ProductRepository) -> None:
    item = _source()
    assert store.get_source(item.source_id) is None
    store.save_source(item)
    store.save_source(item)
    assert store.get_source(item.source_id) == item
    assert store.connection.execute("SELECT count(*) FROM sources").fetchone()[0] == 1


def test_source_immutable_key_conflict(store: ProductRepository) -> None:
    original = _source()
    store.save_source(original)
    with pytest.raises(ConflictError, match="different content"):
        store.save_source(replace(original, content_sha256="b" * 64))
    assert store.get_source(original.source_id) == original


def test_transcript_roundtrip_and_enforced_parent(store: ProductRepository) -> None:
    transcript = TranscriptRevision("transcript-01", "source-01", SHA, "mlx", "base", NOW)
    with pytest.raises(sqlite3.IntegrityError):
        store.save_transcript_revision(transcript)
    store.save_source(_source())
    store.save_transcript_revision(transcript)
    store.save_transcript_revision(transcript)
    assert store.get_transcript_revision("transcript-01") == transcript


def test_exact_evidence_span_roundtrip_and_fk(store: ProductRepository) -> None:
    span = _span()
    with pytest.raises(sqlite3.IntegrityError):
        store.save_span(span)
    store.save_source(_source())
    store.save_span(span)
    store.save_span(span)
    assert store.get_span("span-01") == span
    assert store.get_span("span-01").verify_text(TEXT) == TEXT


def test_node_aliases_and_claim_ids_roundtrip(store: ProductRepository) -> None:
    node = KnowledgeNode(
        "node-01",
        "Flexible structure",
        KnowledgeKind.CONCEPT,
        topic_aliases=("daily systems", "每日安排"),
        source_claim_ids=("claim-01",),
    )
    store.save_node(node)
    store.save_node(node)
    assert store.get_node("node-01") == node


def test_knowledge_node_and_source_cannot_be_saved_public(
    store: ProductRepository,
) -> None:
    with pytest.raises(ContractError, match="private"):
        Source("source-02", SourceOrigin.FILE, SHA, NOW, NOW, privacy_scope="public")
    with pytest.raises(ContractError, match="private"):
        KnowledgeNode("node-01", "Name", KnowledgeKind.CONCEPT, privacy_scope="public")


def test_stored_node_cannot_claim_unapproved_revision(store: ProductRepository) -> None:
    node = KnowledgeNode(
        "node-01", "Topic", KnowledgeKind.CONCEPT, approved_revision_id="revision-01"
    )
    with pytest.raises(ContractError, match="review transaction"):
        store.save_node(node)
    assert store.get_node("node-01") is None


def test_proposal_roundtrip_with_existing_evidence(store: ProductRepository) -> None:
    store.save_source(_source())
    store.save_span(_span())
    store.save_node(KnowledgeNode("node-01", "Topic", KnowledgeKind.CONCEPT))
    proposal = _proposal()
    store.save_proposal(proposal)
    store.save_proposal(proposal)
    assert store.get_proposal(proposal.proposal_id) == proposal
    with pytest.raises(ConflictError):
        store.save_proposal(replace(proposal, rationale="A different explanation"))


def test_proposal_requires_existing_evidence_and_knowledge_node(
    store: ProductRepository,
) -> None:
    store.save_source(_source())
    store.save_node(KnowledgeNode("node-01", "Topic", KnowledgeKind.CONCEPT))
    with pytest.raises(EvidenceError, match="not present"):
        store.save_proposal(_proposal())
    store.save_span(_span())
    with pytest.raises(sqlite3.IntegrityError):
        store.save_proposal(replace(_proposal(), node_id="unknown-node"))


def test_repository_cannot_approve_proposals_or_write_revisions(
    store: ProductRepository,
) -> None:
    store.save_source(_source())
    store.save_span(_span())
    store.save_node(KnowledgeNode("node-01", "Topic", KnowledgeKind.CONCEPT))
    with pytest.raises(ContractError, match="authenticated"):
        store.save_proposal(replace(_proposal(), status=ProposalStatus.APPROVED))
    assert store.get_revision("revision-01") is None
    assert not hasattr(store, "save_revision")


def test_claim_evidence_associations_preserve_order_and_support_polarity(
    store: ProductRepository,
) -> None:
    store.save_source(_source())
    for span_id in ("span-01", "span-02", "span-03"):
        store.save_span(_span(span_id))
    claim = Claim(
        claim_id="claim-01",
        text="A statement tied to source text",
        owner=ClaimOwner.SOURCE,
        modality=ClaimModality.ASSERTION,
        confidence_bucket=Confidence.MEDIUM,
        supporting_span_ids=("span-02", "span-01"),
        opposing_span_ids=("span-03",),
    )
    store.save_claim(claim)
    store.save_claim(claim)
    assert store.get_claim("claim-01") == claim
    with pytest.raises(ConflictError):
        store.save_claim(replace(claim, text="Changed assertion"))
    assert store.connection.execute("SELECT count(*) FROM claim_evidence").fetchone()[0] == 3


def test_claim_insert_rolls_back_on_missing_evidence(store: ProductRepository) -> None:
    store.save_source(_source())
    store.save_span(_span())
    claim = Claim(
        "claim-01", "Claim", ClaimOwner.USER, ClaimModality.HYPOTHESIS,
        Confidence.UNKNOWN, supporting_span_ids=("span-01", "missing-span"),
    )
    with pytest.raises(EvidenceError):
        store.save_claim(claim)
    assert store.get_claim("claim-01") is None


def test_claim_sql_snapshot_cannot_contain_fabricated_span_ids(
    store: ProductRepository,
) -> None:
    store.save_source(_source())
    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute(
            "INSERT INTO claim_evidence (claim_id,span_id,polarity,ordinal) "
            "VALUES (?,?,?,?)",
            ("claim-absent", "span-absent", "supporting", 0),
        )


def test_explicit_transaction_rollback_preserves_empty_store(
    store: ProductRepository,
) -> None:
    conn = store.connection
    conn.execute("BEGIN IMMEDIATE")
    store.save_source(_source())
    store.save_node(KnowledgeNode("node-01", "Topic", KnowledgeKind.CONCEPT))
    conn.execute("ROLLBACK")
    assert store.get_source("source-01") is None
    assert store.get_node("node-01") is None


def test_legacy_source_id_is_not_an_sql_injection_vector(store: ProductRepository) -> None:
    store.save_source(_source())
    assert store.get_source("source-01' OR 1=1--") is None
    assert store.get_source("source-01") is not None
    assert store.connection.execute("SELECT count(*) FROM sources").fetchone()[0] == 1


def test_user_actions_not_yet_enabled_by_persistence(store: ProductRepository) -> None:
    action = ReviewAction(
        "action-01", "proposal-01", "user-01", ReviewDecision.APPROVE,
        NOW, "idempotency-01",
    )
    assert action.decision is ReviewDecision.APPROVE
    assert not hasattr(store, "approve_proposal")
    assert not hasattr(store, "save_review_action")
