"""Validated, immutable private record repositories; never publish or run models.

Repository inserts are idempotent only for byte-for-byte equivalent entities.
Proposal/revision approval is deliberately NOT implemented in ARCH-00B.
"""

from __future__ import annotations

import json
import sqlite3

from xwiki.domain.codec import from_payload, to_payload
from xwiki.domain.enums import ProposalStatus
from xwiki.domain.errors import ContractError, EvidenceError
from xwiki.domain.evidence import Claim, EvidenceSpan
from xwiki.domain.knowledge import KnowledgeNode, KnowledgeRevision
from xwiki.domain.proposal import ChangeProposal
from xwiki.domain.source import Source, TranscriptRevision

from .database import ConflictError


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ProductRepository:
    """Explicitly limited create/read API over the product-only SQLite store.

    Legacy ingest.sqlite is not opened here. `raw/` files are not touched.
    Mutations never imply a Git commit, user approval, or public publication.
    """

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def _get(self, table: str, key: str, value: str) -> dict[str, object] | None:
        # table/key originate solely from hardcoded internal callers.
        row = self.connection.execute(
            f"SELECT * FROM {table} WHERE {key} = ?", (value,)
        ).fetchone()
        return dict(row) if row is not None else None

    def _insert(self, table: str, key: str, record: dict[str, object]) -> None:
        names = tuple(record)
        values = ", ".join("?" for _ in names)
        self.connection.execute(
            f"INSERT INTO {table} ({', '.join(names)}) VALUES ({values}) "
            f"ON CONFLICT({key}) DO NOTHING",
            tuple(record.values()),
        )
        saved = self._get(table, key, str(record[key]))
        if saved != record:
            raise ConflictError(f"{table} ID already exists with different content")

    def get_source(self, source_id: str) -> Source | None:
        row = self._get("sources", "source_id", source_id)
        return from_payload(Source, row) if row is not None else None

    def save_source(self, source: Source) -> None:
        self._insert("sources", "source_id", to_payload(source))

    def get_transcript_revision(self, revision_id: str) -> TranscriptRevision | None:
        row = self._get("transcript_revisions", "revision_id", revision_id)
        return from_payload(TranscriptRevision, row) if row is not None else None

    def save_transcript_revision(self, revision: TranscriptRevision) -> None:
        self._insert("transcript_revisions", "revision_id", to_payload(revision))

    def get_span(self, span_id: str) -> EvidenceSpan | None:
        row = self._get("evidence_spans", "span_id", span_id)
        return from_payload(EvidenceSpan, row) if row is not None else None

    def save_span(self, span: EvidenceSpan) -> None:
        self._insert("evidence_spans", "span_id", to_payload(span))

    def get_node(self, node_id: str) -> KnowledgeNode | None:
        row = self._get("knowledge_nodes", "node_id", node_id)
        if row is None:
            return None
        row["source_claim_ids"] = json.loads(str(row.pop("source_claim_ids_json")))
        row["topic_aliases"] = json.loads(str(row.pop("topic_aliases_json")))
        return from_payload(KnowledgeNode, row)

    def save_node(self, node: KnowledgeNode) -> None:
        if node.approved_revision_id is not None:
            raise ContractError("approval writeback requires the future review transaction")
        payload = to_payload(node)
        payload["source_claim_ids_json"] = _json(payload.pop("source_claim_ids"))
        payload["topic_aliases_json"] = _json(payload.pop("topic_aliases"))
        self._insert("knowledge_nodes", "node_id", payload)

    def get_proposal(self, proposal_id: str) -> ChangeProposal | None:
        row = self._get("change_proposals", "proposal_id", proposal_id)
        if row is None:
            return None
        row["evidence_span_ids"] = json.loads(str(row.pop("evidence_span_ids_json")))
        row["uncertainty_notes"] = json.loads(str(row.pop("uncertainty_notes_json")))
        generator = row.pop("generator_json")
        row["generator"] = json.loads(str(generator)) if generator is not None else None
        row["external_processing_approved"] = bool(row["external_processing_approved"])
        return from_payload(ChangeProposal, row)

    def save_proposal(self, proposal: ChangeProposal) -> None:
        if proposal.status not in {
            ProposalStatus.DRAFT,
            ProposalStatus.PROPOSED,
            ProposalStatus.NEEDS_EVIDENCE,
        }:
            raise ContractError("proposal decisions require a separate authenticated review")
        for span_id in proposal.evidence_span_ids:
            if self.get_span(span_id) is None:
                raise EvidenceError("proposed evidence span is not present in the source store")
        payload = to_payload(proposal)
        payload["evidence_span_ids_json"] = _json(payload.pop("evidence_span_ids"))
        payload["uncertainty_notes_json"] = _json(payload.pop("uncertainty_notes"))
        generator = payload.pop("generator")
        payload["generator_json"] = _json(generator) if generator is not None else None
        payload["external_processing_approved"] = int(
            payload["external_processing_approved"]
        )
        self._insert("change_proposals", "proposal_id", payload)

    def get_revision(self, revision_id: str) -> KnowledgeRevision | None:
        row = self._get("knowledge_revisions", "revision_id", revision_id)
        return from_payload(KnowledgeRevision, row) if row is not None else None

    def get_claim(self, claim_id: str) -> Claim | None:
        row = self._get("claims", "claim_id", claim_id)
        if row is None:
            return None
        evidence = self.connection.execute(
            "SELECT span_id, polarity, ordinal FROM claim_evidence WHERE claim_id=? "
            "ORDER BY polarity, ordinal", (claim_id,)
        ).fetchall()
        row["supporting_span_ids"] = [
            item["span_id"] for item in evidence if item["polarity"] == "supporting"
        ]
        row["opposing_span_ids"] = [
            item["span_id"] for item in evidence if item["polarity"] == "opposing"
        ]
        return from_payload(Claim, row)

    def save_claim(self, claim: Claim) -> None:
        if self.get_claim(claim.claim_id) is not None:
            if self.get_claim(claim.claim_id) != claim:
                raise ConflictError("claim ID already exists with different content")
            return
        for span_id in (*claim.supporting_span_ids, *claim.opposing_span_ids):
            if self.get_span(span_id) is None:
                raise EvidenceError("claim evidence span does not exist")
        payload = to_payload(claim)
        payload.pop("supporting_span_ids")
        payload.pop("opposing_span_ids")
        self.connection.execute("SAVEPOINT save_claim")
        try:
            self._insert("claims", "claim_id", payload)
            for polarity, ids in (
                ("supporting", claim.supporting_span_ids),
                ("opposing", claim.opposing_span_ids),
            ):
                self.connection.executemany(
                    "INSERT INTO claim_evidence (claim_id, span_id, polarity, ordinal) "
                    "VALUES (?, ?, ?, ?)",
                    [
                        (claim.claim_id, span_id, polarity, order)
                        for order, span_id in enumerate(ids)
                    ],
                )
            self.connection.execute("RELEASE SAVEPOINT save_claim")
        except Exception:
            self.connection.execute("ROLLBACK TO SAVEPOINT save_claim")
            self.connection.execute("RELEASE SAVEPOINT save_claim")
            raise
