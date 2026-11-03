"""Application-facing ports. No imports from persistence, model providers or UI."""

from typing import Protocol

from .evidence import EvidenceSpan
from .knowledge import KnowledgeNode, KnowledgeRevision
from .proposal import ChangeProposal
from .source import Source


class SourceStore(Protocol):
    def get_source(self, source_id: str) -> Source | None: ...

    def save_source(self, source: Source) -> None: ...


class EvidenceStore(Protocol):
    def get_span(self, span_id: str) -> EvidenceSpan | None: ...


class ProposalStore(Protocol):
    def get_proposal(self, proposal_id: str) -> ChangeProposal | None: ...

    def save_proposal(self, proposal: ChangeProposal) -> None: ...


class KnowledgeStore(Protocol):
    def get_node(self, node_id: str) -> KnowledgeNode | None: ...

    def get_revision(self, revision_id: str) -> KnowledgeRevision | None: ...


class Clock(Protocol):
    def now_iso8601(self) -> str: ...


class IdGenerator(Protocol):
    def new_id(self) -> str: ...
