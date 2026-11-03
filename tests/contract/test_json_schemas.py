"""JSON Schema contracts are executable and must match Python wire entities."""

import json
from dataclasses import fields
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
import pytest

from xwiki.domain.codec import to_payload
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
from xwiki.domain.evidence import Claim, EvidenceSpan
from xwiki.domain.knowledge import KnowledgeNode, KnowledgeRevision
from xwiki.domain.proposal import ChangeProposal, ReviewAction
from xwiki.domain.source import Source, TranscriptRevision

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"
NOW = "2026-11-03T09:12:00+08:00"
HASH = "a" * 64


def validator(name: str) -> Draft202012Validator:
    schema = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


FIXTURES = [
    ("source.schema.json", Source("source-01", SourceOrigin.FILE, HASH, NOW, NOW)),
    ("transcript-revision.schema.json",
     TranscriptRevision("transcript-01", "source-01", HASH, "mlx", "base", NOW)),
    ("evidence.schema.json", EvidenceSpan("span-01", "source-01", HASH, 0, 5, HASH)),
    ("claim.schema.json",
     Claim("claim-01", "Claim text", ClaimOwner.SOURCE, ClaimModality.ASSERTION,
           Confidence.HIGH, supporting_span_ids=("span-01",))),
    ("knowledge-node.schema.json",
     KnowledgeNode("node-01", "Daily systems", KnowledgeKind.CONCEPT)),
    ("knowledge-revision.schema.json",
     KnowledgeRevision("revision-01", "node-01", HASH, NOW, "user-01", "review-01")),
    ("change-proposal.schema.json", ChangeProposal(
        proposal_id="proposal-01",
        node_id="node-01",
        candidate_kind=ProposalKind.QUALIFY,
        status=ProposalStatus.PROPOSED,
        created_at=NOW,
        before_text="Old",
        after_text="New",
        rationale="New material",
        evidence_span_ids=("span-01",),
        confidence_bucket=Confidence.MEDIUM,
        base_revision_id="revision-01",
    )),
    ("review-action.schema.json",
     ReviewAction("action-01", "proposal-01", "user-01", ReviewDecision.APPROVE, NOW,
                  "idempotency-01")),
]


@pytest.mark.parametrize("schema_name,entity", FIXTURES)
def test_domain_payload_is_valid_against_json_schema(schema_name: str, entity: object) -> None:
    check = validator(schema_name)
    payload = to_payload(entity)
    assert not list(check.iter_errors(payload))
    declared = set(check.schema["properties"])
    assert declared == {field.name for field in fields(entity)}


@pytest.mark.parametrize(
    "schema_name,field,bad",
    [
        ("source.schema.json", "privacy_scope", "public"),
        ("source.schema.json", "content_sha256", "invalid"),
        ("source.schema.json", "imported_at", "2026-01-01"),
        ("source.schema.json", "source_id", "../bad"),
        ("claim.schema.json", "supporting_span_ids", []),
        ("claim.schema.json", "confidence_bucket", "certain"),
        ("evidence.schema.json", "start_offset", -1),
        ("change-proposal.schema.json", "candidate_kind", "fix_everything"),
        ("change-proposal.schema.json", "external_processing_approved", "yes"),
        ("knowledge-node.schema.json", "privacy_scope", "public"),
        ("review-action.schema.json", "decision", "publish"),
    ],
)
def test_schema_rejects_unsafe_or_invalid_input(
    schema_name: str, field: str, bad: object
) -> None:
    fixture = next(item for name, item in FIXTURES if name == schema_name)
    data = to_payload(fixture)
    data[field] = bad
    assert not validator(schema_name).is_valid(data)


@pytest.mark.parametrize("schema_name,entity", FIXTURES)
def test_schema_rejects_unknown_fields(schema_name: str, entity: object) -> None:
    data = {**to_payload(entity), "private_path": "/Users/example/VoiceMemos"}
    assert not validator(schema_name).is_valid(data)


def test_proposal_schema_rejects_unsigned_updates_and_approval_without_evidence() -> None:
    data = to_payload(FIXTURES[6][1])
    data["base_revision_id"] = None
    assert not validator("change-proposal.schema.json").is_valid(data)
    data["base_revision_id"] = "revision-01"
    data["status"] = "approved"
    data["evidence_span_ids"] = []
    assert not validator("change-proposal.schema.json").is_valid(data)


def test_all_schemas_are_canonical_draft_2020_12() -> None:
    paths = sorted(SCHEMAS.glob("*.schema.json"))
    assert len(paths) == len(FIXTURES)
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert data["additionalProperties"] is False
        Draft202012Validator.check_schema(data)
