# UX-002A — Reliable Local Source Import

> Scope: first real private file import; **not yet** Whisper processing, Review Workbench, GUI or app distribution.  
> Depends on ARCH-00A/B/C, X-Wiki main. CI results are authoritative.

## User value

People can finally import **their own actual source bytes**, not a fictional
UX-001 story. The operation is local: it never runs pi, MLX Whisper, Git push,
or GitHub Pages publication. A successful \`stored\` status means the blob
has been copied to owner-private storage, flushed, fsynced and SHA-256 checked,
with a durable SQLite Source record.

## What exists, by file

| File | Role |
|---|---|
| \`src/xwiki/domain/blob.py\` | Immutable BlobReceipt; size, digest, media kind |
| \`src/xwiki/application/import_source.py\` | Port-based ImportSource use case; deterministic Source ID, idempotence |
| \`src/xwiki/infrastructure/file_store.py\` | Immutable local blobs, streamed copy/hash, fsync, file locks, corruption check, explicit export |
| \`src/xwiki/interfaces/import_cli.py\` | Single-machine \`import\`, \`verify\`, \`export\` commands, sanitized JSON output |
| \`tests/integration/source/test_source_import.py\` | Real text/audio import; symlink, corruption, concurrent edit, disk failure, restart, idempotence, export |
| \`pyproject.toml\` | \`xwiki-import\` command |
| \`.github/workflows/macos-smoke.yml\` | Run source import tests on a synthetic macOS runner |

No new schema migration is needed: ARCH-00B already has \`sources\` and a
\`stored\` status. This release does NOT overwrite the earlier legacy
\`recordings\` database, nor edit existing published wiki content.

## Local usage

\`\`\`sh
pip install -e .
xwiki-import import /Users/me/Documents/notes.md
# Copy source_id from returned JSON; it is not the filename.
xwiki-import verify <source_id>
xwiki-import export <source_id> /Users/me/Documents/notes-original-export.md
\`\`\`

Alternatively, run \`python -m xwiki.interfaces.import_cli ...\`. Defaults:
\`.state/product.sqlite\` and \`.state/source-store/\` relative to the
current working directory. Invoke from the X-Wiki repository root.

- Supported original files: UTF-8 \`.txt\`, \`.md\`; structurally recognizable
  \`.m4a\`, \`.mp3\`, \`.wav\`. The audio header check is a lightweight guard,
  **not a full media decoder**; actual transcription tests are UX-002B.
- Default size limits: 16 MiB text, 256 MiB audio. Oversize, empty, invalid
  UTF-8 and invalid audio headers are rejected with no successful Source.
- Store: \`.state/source-store/sha256/aa/<sha256>.blob\`; permissions owner-only
  on supported systems; \`.state/\` stays Git-ignored.
- Stored original bytes never replace the selected input. Two paths with the
  same bytes and origin map to one Source ID; the same path with altered bytes
  becomes a different Source. No automatic source deletion.
- Export explicitly names a **new destination**; existing files cannot
  be overwritten. Users must not choose a tracked public Wiki path for
  exporting private material.
- CLI returns only status, Source ID, SHA-256, byte count, kind and duplicate
  flag; does not emit filename or source text.

## Crash and data integrity semantics

1. Read a regular input file; reject symlinks and unrecognized formats.
2. Copy streamed chunks into private incoming tempfile; compute hash during
   copy, decode text incrementally and confirm source file has not changed.
3. fsync tempfile, then under a private file lock reuse verified matching blob
   or atomically rename new blob and fsync its directory.
4. Only then write Source into the product SQLite store as \`stored\`.
5. On interruption before SQLite insert, the immutable blob can be an orphan,
   not a false-success Source; next import finds and reuses it.
6. On re-open, \`verify\` recalculates SHA-256 from stored bytes. Missing or
   corrupted blobs cause an error; no fake 'success' status is returned.
7. If a disk or other exception occurs while copying, the private tempfile
   is removed and no new Source row is written.

**Limitation:** no managed orphan cleanup and no durable upload job table yet.
UX-002B will add lifecycle events, retries, cancellation, real ASR,
and a repair-oriented status update. This phase cannot claim that source
capture works for Apple Voice Memos permission peculiarities until the
Mac adapter and real-device E2E are exercised.

## Acceptance

- Real UTF-8 Chinese/emoji Markdown survives import, process restart,
  SHA verification and export without byte changes.
- Duplicates coalesce; same filename with different bytes does not.
- Invalid text/headers, symlinks, corrupted destination blob and changed
  input are rejected.
- Injected mid-copy failure and injected DB failure never record a new
  false-success Source. Re-running after the failure is idempotent.
- Linux full CI and synthetic macOS core smoke must pass; this is NOT yet
  full real Apple Silicon/iCloud/MLX validation.

## Next milestones

UX-002B: job queue, file-type-dependent processing, live MLX Whisper
adapter, retry and duplicate worker safety.

UX-002C: owner-private IPC/desktop interface and explicit model/privacy
metadata.

UX-002D: no-terminal macOS import experience and real user studies.
