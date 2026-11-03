# PR-006: Durable compilation writeback

Temporary agent workspaces protect the live Wiki from ordinary failed runs.
This follow-up protects it from interrupted multi-file writeback.

### State machine

1. A staging candidate passes path, symlink and source-tree validation.
2. Take a snapshot and enter the exclusive compile-write lock.
3. Verify that the live snapshot still matches the pre-compilation view.
4. Persist original file bytes with SHA-256 integrity checks under
   `.state/compile-transactions/<id>/backups/`. Flush each backup.
5. Write an atomic `journal.json` marked `prepared`; flush the journal and
   its directory **before touching the live Wiki**.
6. Apply each file using same-directory atomic replacement and sync its
   parent directory.
7. Write `committed` to the journal and clean the transaction directory.

### Crash recovery

At the beginning of every ingestion run, and before standalone compilation,
incomplete `prepared` transactions are scanned. For every file, recovery
requires its current SHA to match **either** the recorded old SHA or the
candidate SHA. If any file contains an unexpected manual edit, recovery
stops *before writing anything* and reports a conflict. Otherwise originals
are restored, and the interrupted compilation may be retried.

`committed` transactions are retained only if cleanup was interrupted;
recovery removes their journal without rolling back successfully written
Wiki pages. Crashes during journal preparation are safe because no live
files have yet been modified.

This is crash-recoverable compensation, **not a globally atomic filesystem
transaction**: another reader can briefly observe a mixed tree between
individual file swaps. Continue to use the ingestion flock and avoid direct
concurrent writes to the knowledge layer.

### Verification

- interruption injection with `KeyboardInterrupt` after the first write;
- recovery to the original complete file set;
- conflict detection preserving later manual edits;
- path traversal and symlink rejection;
- durable-journal cleanup on success;
- full Linux CI and synthetic macOS CI.

All private checkpoint and backup material stays in Git-ignored
`.state/`; it is not included in the public knowledge release.
