# PR-004: Release Gate, Manifest, Fault Injection and Evaluation

## Trust and deployment states

The macOS worker compiles changes into the knowledge layer and invokes
`git_publish()`. Publication is considered confirmed **only if the remote Git
branch points to the exact local commit**. Git confirmation does not assert
that a website has deployed successfully.

The release transaction has two durable journal states:

1. `prepared`: a commit-specific manifest has been written locally; remote
   publication is not yet confirmed (it may already have happened).
2. `git_confirmed`: `git ls-remote` verified the exact commit SHA after
   Git push, or found that SHA already published during recovery.

The journal is stored only in `.state/releases/` and is Git-ignored.
Each record captures `schema_version`, `commit_sha`, `content_sha256`, sorted
`files` (public knowledge paths and Git blob hashes), destination remote name
and branch, status, and update timestamp. It does not contain raw sources,
transcripts, remote URLs or credentials.

`scripts/release_gate.py` prints a deterministic, read-only release manifest
of the committed HEAD; this manifest is also included in the built Pages
artifact as `release-manifest.json`.

### Recovery protocol

- Run deterministic Wiki lint before committing any knowledge files.
- Commit only the approved `wiki/`, `index.md` and `log.md` paths.
- Compute a manifest from the **committed** Git HEAD, not dirty working files.
- Write `prepared` using a same-directory temporary file, file fsync, atomic
  replace and directory fsync (when supported).
- Check the remote ref. Push HEAD only when it does not already match.
- Verify the remote ref again and only then record `git_confirmed`.
- If a crash occurs after push but before journal or SQLite confirmation,
  the next run observes the remote HEAD and safely completes confirmation.
- On failures, keep the ingestion DB's `publish_pending` state unchanged,
  so the existing launchd rescan can retry.

The local journal's per-file digest does not include source audio or raw
transcript content. SHA-256 of sorted Git blob identities is a reproducibility
fingerprint and does not replace end-to-end content/signature verification.

## Independent evaluation

`evaluation/golden/wiki_cases.json` contains deliberately authored *synthetic*
fixtures for invalid citations, unsafe links, secrets, duplicate IDs, and
legacy Markdown compatibility. `scripts/evaluate_wiki.py` materializes
each case in a temporary directory and checks observed error codes against
the stored expected results. It returns a nonzero exit status on mismatch.

This is not an LLM semantic quality benchmark. It measures deterministic
schema/link/privacy gate behavior. Real-world source-grounded claim
evaluation requires separately licensed and anonymized transcripts,
human-reviewed labels and an isolated data retention policy.

## Continuous integration

```bash
ruff check .
pytest
python scripts/evaluate_wiki.py
python scripts/wiki_lint.py --strict
python scripts/prepare_site.py --strict
mkdocs build --strict
```

GitHub Pages has its own Quality job prerequisite, so a deployment cannot
continue solely because site rendering succeeds while tests or independent
golden checks fail.

## Remaining limits and next steps

- Git and SQLite form two different durable systems; there is no shared
  cross-system transaction. Recovery is based on checking the actual remote.
- GitHub Pages deployment state needs a separate deployed-commit receipt;
  `git_confirmed` must not be presented as "website deployed".
- Publication can still conflict with unrelated manual Git changes; the
  existing knowledge-file worktree lock reduces but does not remove this risk.
- Unexpected termination during the window after a knowledge commit but
  before the journal is written leaves a commit on local HEAD. Retrying
  `git_publish()` recreates a journal for that HEAD.
- File copy/sandbox and broader privacy policy improvements remain separate.

### Private voice references

An unaliased `[[raw/voice/...]]` renders as a neutral `本地证据` label,
not the original recording filename or identifier. Explicit source aliases
remain subject to public privacy review; they are not assumed safe.
