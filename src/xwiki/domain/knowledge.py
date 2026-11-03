"""Knowledge identity and immutable history are distinct from private sources."""

from dataclasses import dataclass

from .enums import KnowledgeKind, NodeStatus, PrivacyScope
from .errors import ContractError
from .validation import (
    digest,
    enum_value,
    identifier,
    optional_identifier,
    refs,
    required_text,
    timestamp,
)


@dataclass(frozen=True, slots=True)
class KnowledgeNode:
    node_id: str
    title: str
    kind: KnowledgeKind
    approved_revision_id: str | None = None
    privacy_scope: PrivacyScope = PrivacyScope.PRIVATE
    status: NodeStatus = NodeStatus.ACTIVE
    source_claim_ids: tuple[str, ...] = ()
    topic_aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        identifier(self.node_id, "node_id")
        required_text(self.title, "title")
        enum_value(self.kind, KnowledgeKind, "kind")
        optional_identifier(self.approved_revision_id, "approved_revision_id")
        if self.privacy_scope is not PrivacyScope.PRIVATE:
            raise ContractError("knowledge is private; publication needs separate authorization")
        enum_value(self.status, NodeStatus, "status")
        refs(self.source_claim_ids, "source_claim_ids")
        if not isinstance(self.topic_aliases, tuple):
            raise ContractError("topic_aliases must be a tuple")
        for title in self.topic_aliases:
            required_text(title, "topic_aliases")
        if len(self.topic_aliases) != len(set(self.topic_aliases)):
            raise ContractError("topic_aliases contains duplicates")


@dataclass(frozen=True, slots=True)
class KnowledgeRevision:
    revision_id: str
    node_id: str
    content_sha256: str
    committed_at: str
    approved_by: str
    idempotency_key: str
    parent_revision_id: str | None = None
    approved_from_proposal: str | None = None
    undo_of_revision: str | None = None

    def __post_init__(self) -> None:
        identifier(self.revision_id, "revision_id")
        identifier(self.node_id, "node_id")
        digest(self.content_sha256, "content_sha256")
        timestamp(self.committed_at, "committed_at")
        identifier(self.approved_by, "approved_by")
        identifier(self.idempotency_key, "idempotency_key")
        optional_identifier(self.parent_revision_id, "parent_revision_id")
        optional_identifier(self.approved_from_proposal, "approved_from_proposal")
        optional_identifier(self.undo_of_revision, "undo_of_revision")
        if self.parent_revision_id == self.revision_id:
            raise ContractError("a revision cannot be its own parent")
        if self.undo_of_revision == self.revision_id:
            raise ContractError("a revision cannot undo itself")
