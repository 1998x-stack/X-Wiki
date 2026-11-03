-- All knowledge and evidence remain private at the storage level.
CREATE TABLE transcript_revisions (
    revision_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    text_sha256 TEXT NOT NULL CHECK (length(text_sha256) = 64),
    engine TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (source_id, text_sha256, engine, model)
);
CREATE INDEX transcript_by_source ON transcript_revisions(source_id);

CREATE TABLE evidence_spans (
    span_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    source_revision_sha256 TEXT NOT NULL CHECK (length(source_revision_sha256) = 64),
    start_offset INTEGER NOT NULL CHECK (start_offset >= 0),
    end_offset INTEGER NOT NULL CHECK (end_offset > start_offset),
    quote_sha256 TEXT NOT NULL CHECK (length(quote_sha256) = 64),
    transcript_revision_id TEXT REFERENCES transcript_revisions(revision_id),
    start_ms INTEGER CHECK (start_ms IS NULL OR start_ms >= 0),
    end_ms INTEGER CHECK (end_ms IS NULL OR end_ms >= 0),
    CHECK (start_ms IS NULL OR end_ms IS NULL OR end_ms > start_ms)
);
CREATE INDEX evidence_by_source ON evidence_spans(source_id);

CREATE TABLE claims (
    claim_id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    owner TEXT NOT NULL CHECK (owner IN ('user','source','assistant_inference')),
    modality TEXT NOT NULL CHECK (modality IN ('assertion','hypothesis','question')),
    confidence_bucket TEXT NOT NULL CHECK (confidence_bucket IN ('high','medium','low','unknown'))
);
CREATE TABLE claim_evidence (
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    span_id TEXT NOT NULL REFERENCES evidence_spans(span_id),
    polarity TEXT NOT NULL CHECK (polarity IN ('supporting','opposing')),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    PRIMARY KEY (claim_id, span_id, polarity)
);

CREATE TABLE knowledge_nodes (
    node_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('concept','decision','project','entity')),
    approved_revision_id TEXT,
    privacy_scope TEXT NOT NULL DEFAULT 'private' CHECK (privacy_scope = 'private'),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    source_claim_ids_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(source_claim_ids_json)),
    topic_aliases_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(topic_aliases_json))
);

CREATE TABLE change_proposals (
    proposal_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL REFERENCES knowledge_nodes(node_id),
    candidate_kind TEXT NOT NULL CHECK (candidate_kind IN
        ('new','enrich','qualify','contradict','no_change','uncertain')),
    status TEXT NOT NULL CHECK (status IN
        ('draft','proposed','needs_evidence','approved','rejected','superseded','failed')),
    created_at TEXT NOT NULL,
    before_text TEXT NOT NULL,
    after_text TEXT NOT NULL,
    rationale TEXT NOT NULL,
    evidence_span_ids_json TEXT NOT NULL CHECK (json_valid(evidence_span_ids_json)),
    confidence_bucket TEXT NOT NULL CHECK (confidence_bucket IN ('high','medium','low','unknown')),
    base_revision_id TEXT,
    uncertainty_notes_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(uncertainty_notes_json)),
    generator_json TEXT CHECK (generator_json IS NULL OR json_valid(generator_json)),
    external_processing_approved INTEGER NOT NULL DEFAULT 0
        CHECK (external_processing_approved IN (0,1))
);
CREATE INDEX proposals_by_status ON change_proposals(status, created_at);
CREATE INDEX proposals_by_node ON change_proposals(node_id);

-- Private revision history is separate from publication. No automatic Git push.
CREATE TABLE knowledge_revisions (
    revision_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL REFERENCES knowledge_nodes(node_id),
    parent_revision_id TEXT REFERENCES knowledge_revisions(revision_id),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    committed_at TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    approved_from_proposal TEXT REFERENCES change_proposals(proposal_id),
    undo_of_revision TEXT REFERENCES knowledge_revisions(revision_id),
    CHECK (parent_revision_id IS NULL OR parent_revision_id != revision_id),
    CHECK (undo_of_revision IS NULL OR undo_of_revision != revision_id)
);
CREATE INDEX revisions_by_node ON knowledge_revisions(node_id, committed_at);

CREATE TABLE review_actions (
    action_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL REFERENCES change_proposals(proposal_id),
    reviewer_id TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approve','reject','mark_uncertain')),
    reviewed_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE
);
