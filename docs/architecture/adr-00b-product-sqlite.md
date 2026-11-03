# ADR-00B — Private Product SQLite, Versioned Migrations & Legacy Snapshots

Status: **implemented pending CI review** · 2026-11-03  
Stage: [ARCH-00](../product/stages/ARCH-00-Foundation.md) · Depends on [ARCH-00A](adr-00a-domain-boundaries.md)

## Decision: never upgrade the active ingest.sqlite in place

The current `scripts/process_voice_memos.py` owns `.state/ingest.sqlite` and
its `recordings` table. Its current automation and Git behavior MUST continue
to work unchanged while the new product mode is under development.

ARCH-00B creates **another SQLite database** at `.state/product.sqlite`.
Its `schema_migrations` table pins filename + SHA-256 for three migrations:

1. `0001_sources.sql`: private `sources`, versioned full-fidelity legacy
   recording snapshots, conversion issues;
2. `0002_knowledge.sql`: verified-reference shapes, claims, nodes, proposals,
   private revision history, future review action table;
3. `0003_jobs.sql`: product job and attempt tables (no scheduler yet).

Each migration uses explicit `BEGIN IMMEDIATE / COMMIT` and rolls back every
DDL statement in a failed migration. Do **not** replace this with
`sqlite3.executescript`, which can commit the caller's pending transaction.
Checksum drift, unknown future schema versions and foreign-key corruption
make the open fail rather than silently repair or overwrite user data.

### Commands

All commands below must be run in the project root using the installed
`xwiki-knowledge` package, for example after `pip install -e .`.

```bash
# Check old DB without creating/changing the new DB.
python -m xwiki.infrastructure.sqlite.cli --import-legacy --dry-run

# Create/update only the NEW private product database; no legacy data import.
python -m xwiki.infrastructure.sqlite.cli

# Explicit, repeatable import from old recording rows into the NEW DB.
python -m xwiki.infrastructure.sqlite.cli --import-legacy

# Custom locations, without echoing raw private paths in CLI output.
python -m xwiki.infrastructure.sqlite.cli \
  --database .state/product.sqlite --legacy .state/ingest.sqlite --import-legacy
```

`xwiki-state` is an installed console-script alias. The CLI emits only schema
version, row totals, sanitized issue counts and SQLite integrity status.
No import, schema operation or repository method performs LLM calls, Git push,
or Pages publication. Legacy import is **opt-in**.

## Legacy import semantics

- Read old `recordings` through SQLite URI `mode=ro` in a read transaction;
  see committed WAL rows without altering the legacy table/schema.
- Copy every legacy row's original field values into private
  `legacy_recording_snapshots`. New versions of the same recording append a
  second snapshot, keyed by deterministic content hash. This includes raw
  absolute paths and error text: **never export this table**.
- For a valid old lowercase audio SHA, create a deterministic private Source ID
  derived from recording ID + audio SHA. This is a **placeholder record**:
  status `queued` means a later UX-002 importer MUST verify actual file bytes.
  Previously failed recordings become `failed_retryable`.
- Invalid historical SHA: retain the full original snapshot and a
  `legacy_migration_issues` row; do **not** manufacture a Source.
  Unknown old statuses are likewise flagged.
- No imported transcript revision is manufactured without verifying the
  content bytes. Existing `raw_path`/`transcript_path` are recorded privately
  for future migration but their existence/content are NOT trusted yet.
- Full import runs inside one product-side `BEGIN IMMEDIATE`, so a simulated
  failure cannot leave a half-imported batch. Re-run after failure; unchanged
  snapshots do not duplicate. Old legacy DB remains the working source of
  truth for the old CLI until a separate, tested cutover.

## Storage API limits

`ProductRepository` exposes create/read for Source, TranscriptRevision,
EvidenceSpan, Claim, KnowledgeNode and **unapproved** ChangeProposal. Repeated
identical inserts are no-ops; attempts to mutate existing immutable IDs
raise `ConflictError`. Foreign-key and SQL-level privacy checks are active.

**No repository method can approve a revision or publish a file**. The
`knowledge_revisions` and `review_actions` tables are reserved for the
future approval transaction. They are not a substitute for verified evidence,
version CAS, user authentication, permission-gated model invocation, or
atomic SQLite+Markdown writeback. That work belongs to ARCH-00C/UX-003.

## Privacy and file permissions

- Create new `.state/` directory with owner-only permissions where possible.
  New SQLite file mode is `0600`; SQLite WAL inherits compatible permissions.
- Reject symlink database paths and symlinked immediate parents.
- New Source/KnowledgeNode domain objects encode `privacy_scope=private`.
  SQL enforces the same rule; private filesystem paths live only in the
  restricted migration snapshot table, not in domain export or Pages.
- `.state/` remains Git-ignored. A user-specified database outside `.state/`
  must be stored somewhere private; **do not** place it under the public Wiki
  or commit it to Git.
- Protect and backup old `ingest.sqlite` using standard SQLite consistent
  backup tools if the operator needs an independent backup. This migration
  never runs UPDATE, CREATE or DELETE against it.
- Do not treat locally configured pi model providers as implicitly trusted:
  these repositories do not intercept or authorize legacy external calls.

## Recovery and deployment checklist

1. Run read-only preview to count old recordings and malformed SHA rows.
2. Run the explicit import. Check `scanned`, `added_snapshots`,
   `flagged_rows` and integrity result.
3. Re-run the import; unchanged data should report zero new snapshots.
4. For errors, leave `ingest.sqlite` untouched; copy or delete the NEW product
   DB only after preserving any later product-only data (there is none in
   ARCH-00B). Never delete the legacy DB.
5. Run Python unit/integration, macOS synthetic smoke, strict Wiki build,
   and browser regression. A passing CI confirms no runtime behavior
   regression; **it does not confirm live Apple Silicon ingestion or final
   production privacy gating**.

## Why not in-place migration?

An in-place approach could introduce new table locks and migration errors in
the single-user launchd pipeline and undermine existing retry behavior. A
separate store adds temporary dual-DB complexity, but enables safe, explicit
cutover after the actual SourceStore and Approval workflow exist.

### Exit criteria

- SQL migration failure injection rolls back all schema changes in the failed
  version; re-run succeeds.
- Existing `ingest.sqlite` can be passed accidentally without any schema
  or file-byte modification.
- Historical rows with invalid hashes remain auditable; valid sources never
  claim their bytes were verified when they were not.
- Same legacy batch can be imported repeatedly and after an interrupted import
  without duplicate snapshots or silent information loss.
- Legacy CLI is unchanged; full old and new tests remain green.


## Addendum — UX-002B migration 0004 (2026-11-03)

UX-002B extends the **new** `product.sqlite` with
`0004_job_leases.sql` (model identity, lease token/deadline, retry-after,
attempt budget, revision pointer and claim indices). The earlier three SQL
migration contents and checksums remain unchanged. `SCHEMA_VERSION` becomes
4 and wheel packaging tests require all four SQL files. This does **not**
affect the legacy `ingest.sqlite` or the original publisher.
See [UX-002B](../product/stages/UX-002B-Implementation.md).
