# ADR-00A — Pure Contracts Before Product I/O

Status: accepted for ARCH-00A implementation, 2026-11-03. Supersedes no
legacy pipeline code. Related stage: [ARCH-00](../product/stages/ARCH-00-Foundation.md).

## Decision

Build an installable Python 3.10-compatible `xwiki` package in `src/` before
introducing a database migration, model provider, desktop application or
publication workflow. Expose frozen dataclasses for Source, TranscriptRevision,
EvidenceSpan, Claim, KnowledgeNode, KnowledgeRevision, ChangeProposal and
ReviewAction. Expose strict JSON-compatible wire conversion with unknown-key
rejection. Pin eight external Draft 2020-12 JSON Schema contracts and exercise
them with an independent `jsonschema` validator in tests.

Use explicit UTF-8 **byte offsets** into a SHA-256-pinned text revision for
EvidenceSpan, not Python character or JavaScript UTF-16 offsets. Verify exact
byte identity and Unicode boundaries; **do not** confuse string matching with
semantic evidence support.

## Trust boundaries and invariants

- Private Source/KnowledgeNode contracts cannot be serialized as public.
- External model transfers are denied without an explicit matching consent
  value. Publication is always denied at this domain-only stage.
- A ChangeProposal cannot modify approved content through construction alone.
  The pure status transition is **not** an authenticated approval operation;
  evidence resolution, optimistic concurrency control, durable writeback and
  audit logs belong to ARCH-00B/C and UX-003.
- Private absolute filesystem locations are intentionally **absent from wire
  Source entities**; an eventual SourceStore must map stable IDs to paths only
  inside a restricted local store.
- The current `scripts/compile_wiki.py` and `process_voice_memos.py` are
  not switched to the new contracts in this PR. They retain their legacy
  behavior, including the existing Git push default. This PR does not claim
  any already-running full privacy isolation.
- `raw/references/` may be tracked in the current public Git repository;
  new Source records must not be placed there.

## Alternatives considered

1. Directly convert `scripts/` to a SaaS API: rejected because it would
   compound current privacy/approval semantics before they are tested.
2. Introduce Pydantic as a production dependency now: deferred; stdlib
   dataclasses + strict JSON Schema are sufficient for pure models. Runtime
   adapter choices remain open.
3. Add a `public` value to every object and allow it by default: rejected.
   Publication requires a separately authenticated, explicit action.
4. Use Unicode codepoint offsets: rejected as ambiguous across Python,
   JavaScript and audio-to-text serializers. UTF-8 byte offsets are portable
   when hash and boundary checks are enforced.

## Definition of done

- `pip install -e .` and `from xwiki.domain.source import Source` work.
- Every entity is immutable and rejects invalid IDs, SHA-256 hashes, dates,
  enums, spans or unauthorized public scope.
- Python wire roundtrip and independent JSON Schema validation agree on
  valid examples and reject unsafe negatives.
- Existing CLI tests, Wiki lint, strict MkDocs build and Chromium UI E2E
  remain green; macOS synthetic smoke also validates pure domain models.

## Explicitly out of scope

SQLite schema, migration, provider adapters, evidence inference, real user
review UI, Git publication approval, authentication, Apple Silicon MLX E2E.
