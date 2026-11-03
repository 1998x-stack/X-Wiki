# PR-002 — Staged compiler workspace

The pi subprocess now runs in a disposable workspace containing copies of
`raw/`, `wiki/`, `index.md`, `log.md`, and the compiler skill. The real
repository is not the default working directory of the model.

## Commit protocol

1. Verify source files resolve under the repository's `raw/` directory.
2. Snapshot live tracked-and-source files before compiling.
3. Copy the minimum input tree into a temporary workspace.
4. Run pi against the workspace. Any timeout or subprocess failure discards it.
5. Recheck the live tree, reject stage symlinks and unexpected staged edits.
6. Confirm that the live tree has not changed since the snapshot.
7. Apply changed knowledge files individually using atomic replacement. On
   failure, restore all prior file contents from memory.

No Git push or state update is handled here. The existing pipeline only marks
sources `raw_ready` as compiled after this function returns normally.

## Security and durability limits

- **Not an operating-system sandbox.** pi and its tooling could theoretically
  access files outside staging using absolute paths. Filesystem confinement
  must be implemented separately (e.g., an OS-specific sandbox).
- The temporary workspace may contain sensitive raw transcripts. It is
  restricted by the OS's temporary-directory permissions and removed after
  execution. Remote LLM-provider requests have a separate privacy boundary.
- Multi-file apply is not one atomic transaction: rollback is best effort on
  disk errors or power loss. A follow-up change should use a durable recovery
  journal or versioned worktree publication strategy.
- Repo snapshots have O(repository-bytes) cost. Consider staged manifest
  hashes if the raw source collection becomes large.

## Tests

`pytest scripts/tests/test_staged_compiler.py -q` validates staging,
timeout cancellation, unauthorized writes, symlink escape rejection,
concurrent edits, and rollback.
