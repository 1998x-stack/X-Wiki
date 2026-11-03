# ARCH-00B — SQLite v2 Foundation: Implementation & Acceptance

> Stage delivered to PR; CI results must be verified before marking the work
> merged. This is a **storage layer**, not a consumer app and not final
> publication-privacy enforcement.

## Work packages and files

| Package | Implemented paths | Acceptance |
|---|---|---|
| MIG-01 Schema | `src/xwiki/infrastructure/sqlite/migrations/0001_*.sql`, `0002_*.sql`, `0003_*.sql` | sources/transcripts/evidence/knowledge/proposals/revisions/jobs all exist and enforce FKs/privacy |
| MIG-02 Engine | `src/xwiki/infrastructure/sqlite/database.py` | version+SHA migration ledger; WAL/FULL sync; each migration atomic; legacy DB refusal |
| MIG-03 Private repositories | `src/xwiki/infrastructure/sqlite/repositories.py` | strict dataclass roundtrip, immutable insert, conflicts, existing evidence IDs; no approval methods |
| MIG-04 Legacy import | `src/xwiki/infrastructure/sqlite/legacy.py` | read-only ingest.sqlite with WAL; all rows preserved in versioned private snapshots; invalid hash flagged |
| MIG-05 CLI | `src/xwiki/infrastructure/sqlite/cli.py` | dry-run, explicit opt-in import, redacted aggregate JSON output |
| MIG-06 Reliability | `tests/integration/sqlite/*`, `.github/workflows/*` | migrations, rollback, idempotence, integrity, foreign keys, legacy compatibility, macOS smoke |
| MIG-07 Docs | `docs/architecture/adr-00b-product-sqlite.md` | real user can understand data ownership, migration/recovery, privacy limits |

## Legacy status preservation

The old `recordings` `status` is copied verbatim in a local snapshot.
The new Source is `queued` or `failed_retryable` because no raw audio
file has actually been copied or hash-verified by the new importer.
`compiled/publish_pending` is **not** translated into `indexed` and
does not carry a publish authorization.

A checksum-invalid recording has a snapshot and issue but no fabricated Source.
On subsequent runs, unchanged snapshots are skipped. Changed historical rows
append new snapshots so history isn't overwritten.

## Explicit exclusions

- No change to `scripts/process_voice_memos.py` or legacy `open_state`.
- No auto-approval, no Git push, no model calls, no new desktop UI.
- No opening of private source paths from web or remote network endpoints.
- No actual copied media blobs yet; UX-002 will implement verified SourceStore.
- No SQLite/Markdown two-system atomic approval transaction; UX-003 owns it.

## Subsequent tasks

ARCH-00C: prevent the new product branch from automatically becoming public
Markdown/Git content. UX-002A: verify and copy source files into immutable
private content storage, then advance source state from queued to stored.
