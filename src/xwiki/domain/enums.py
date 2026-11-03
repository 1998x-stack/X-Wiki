"""Stable wire values shared with JSON Schema. Python 3.10 compatible."""

from enum import Enum


class WireEnum(str, Enum):
    """A string enum, usable as a JSON string without requiring StrEnum."""


class SourceOrigin(WireEnum):
    VOICE_MEMO = "voice_memo"
    FILE = "file"
    MARKDOWN_VAULT = "markdown_vault"
    MANUAL = "manual"


class SourceStatus(WireEnum):
    QUEUED = "queued"
    STORED = "stored"
    TRANSCRIBING = "transcribing"
    INDEXED = "indexed"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_TERMINAL = "failed_terminal"


class PrivacyScope(WireEnum):
    PRIVATE = "private"
    PUBLIC = "public"


class DataDestination(WireEnum):
    DEVICE = "device"
    EXTERNAL_MODEL = "external_model"
    PUBLIC_WEB = "public_web"


class KnowledgeKind(WireEnum):
    CONCEPT = "concept"
    DECISION = "decision"
    PROJECT = "project"
    ENTITY = "entity"


class NodeStatus(WireEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ClaimOwner(WireEnum):
    USER = "user"
    SOURCE = "source"
    ASSISTANT_INFERENCE = "assistant_inference"


class ClaimModality(WireEnum):
    ASSERTION = "assertion"
    HYPOTHESIS = "hypothesis"
    QUESTION = "question"


class Confidence(WireEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ProposalKind(WireEnum):
    NEW = "new"
    ENRICH = "enrich"
    QUALIFY = "qualify"
    CONTRADICT = "contradict"
    NO_CHANGE = "no_change"
    UNCERTAIN = "uncertain"


class ProposalStatus(WireEnum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    NEEDS_EVIDENCE = "needs_evidence"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    FAILED = "failed"


class ReviewDecision(WireEnum):
    APPROVE = "approve"
    REJECT = "reject"
    MARK_UNCERTAIN = "mark_uncertain"
