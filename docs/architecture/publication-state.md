# PR-001 — Publication state correctness

`git_publish()` must either complete the Git push and return a `PublishResult`
(commit SHA, remote, branch) or raise an error. Missing repositories and remotes are
not successful publications.

The ingestion state is deliberately backward-compatible:

- `raw_ready`: ready to compile;
- `publish_pending`: compilation completed and publication not yet confirmed;
- `compiled`: in auto-publish mode, the push completed successfully; in
  `--skip-push` or `XWIKI_GIT_PUSH=false` mode, the output is only compiled.

The distinction between compiled and published will be represented by separate
records in a later state schema. Avoid inferring actual remote status merely from
the word `compiled` for past rows.

## Failure semantics

- No .git or missing remote: raise `RuntimeError`, retain `publish_pending`.
- Failed push: raise `CalledProcessError`, retain `publish_pending`.
- Successful push, then crash before SQLite update: push the same HEAD on retry
  (idempotent); only then mark rows compiled.
- The pipeline returns exit status 75 on transient publication failure.

Run `pytest scripts/tests/test_publication.py -q` for publication regressions.
