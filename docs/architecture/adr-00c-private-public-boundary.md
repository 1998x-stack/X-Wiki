# ADR-00C — Separate private candidate review from public Wiki promotion

Status: **implemented; verify CI before merging** (2026-11-03).  
Depends: ARCH-00A/B. Next: UX-002 source capture and UX-003 verified knowledge review.

## Two intentionally separate modes

**Existing CLI compatibility:** When XWIKI_PIPELINE_MODE is not specified,
\`legacy\` preserves the existing direct staged Wiki compilation, optional Git
commit and push, and publish_pending retry behavior. XWIKI_GIT_PUSH retains
its historical default. This **does not mean legacy mode is safe for private
source content**. Users must opt out of legacy mode to use new privacy gates.

**Review-first:** Set XWIKI_PIPELINE_MODE=review_first. It never takes the
automatic git_publish branch, even if XWIKI_GIT_PUSH=true and legacy pending
rows exist. It only creates immutable per-candidate directories in the
gitignored .state/review-candidates directory after validation of a throwaway
staged compilation. Original Wiki/index/log files remain unchanged.
A candidate generated with no meaningful diff records a no-change state;
the model is not required to invent new pages.

The pi provider may call remote AI and staged tools are not a process sandbox.
\`XWIKI_ALLOW_MODEL_EGRESS=false\` denies invoking pi in review-first mode.
The operator must explicitly set it to true to invoke their configured provider.
**Do not interpret this boolean as a per-document consent, a network firewall,
or an approved third-party model contract**; those belong to subsequent product
work.

## Operator commands (manual, not a consumer release)

\`\`\`sh
# 1. Enable review-first in .env (read privacy notes before allowing pi).
XWIKI_PIPELINE_MODE=review_first
XWIKI_ALLOW_MODEL_EGRESS=false

# 2. Run the old CLI in review-first mode or explicitly create a candidate.
python scripts/compile_wiki.py raw/voice/example.md --proposal-only --allow-model-egress

# 3. Preview EXACT private candidate ID.
python scripts/private_review.py show <candidate_sha256>

# 4. Private file-level acceptance: stores a copy under .state/ only.
python scripts/private_review.py approve <candidate_sha256> --confirm <candidate_sha256>

# 5. Independent local public worktree promotion; requires the digest printed by 'show'.
python scripts/private_review.py promote <candidate_sha256> --confirm-public <public_digest>
\`\`\`

Commands 2–5 are examples; the example source must exist. Preview prints
candidate content (possibly private) to your local terminal. It does not send
it to a provider or webpage. The public digest is deterministic and is an
**explicit-review confirmation, not an authentication secret**.

Approving privately does NOT update an approved KnowledgeRevision in SQLite:
this phase provides an initial *file-based candidate and approval bundle*,
not the product's verified evidence/identity/CAS workflow. The next UX-003
phase will implement actual semantic evidence checking, versioned knowledge
writeback and user authorization. Do not describe the local copy as full
source-backed review.

Public promotion:
- requires a distinct confirmation after private approval;
- checks candidate byte integrity and compares live file bases;
- builds a disposable full Wiki preview and runs wiki_lint;
- writes to public files only via durable compilation transaction;
- creates .state/public-promotions intent **before** any modifications, and
  marks it applied locally afterward; after interrupted writes, the existing
  compilation journal is the recovery mechanism;
- does not stage, commit, push, or deploy on its own.

A subsequent operator-directed Git publication is still separate. Existing
Git/Pages workflows for the **legacy Wiki** are intentionally preserved.

## Threat model, negative tests and limits

- Rejected: unapproved candidate applied to public Wiki, stale before-hash,
  malformed candidate, corrupted blob, symlink reference, unsafe destination,
  invalid Wiki source provenance, private frontmatter on published Wiki pages.
- Never promoted automatically from review-first ingestion, including restart
  with a pre-existing legacy publish_pending row.
- The public Wiki remains on a Git branch with other tracked files. In the
  legacy mode the existing Git push may push *all committed tracked data*,
  not just the manifest-listed Wiki files. Do not commit private content.
- The source snapshot still includes raw/; malicious pi commands are NOT
  isolated by OS sandbox or network controls. Use only trusted/configured
  providers, and avoid sensitive recordings until UX-002/003 complete.
- Legacy GitHub Pages may remain unchanged for the public site; it is not a
  private user workspace. Existing heuristic Wiki Lint is **not a proof**
  of anonymization or absence of all sensitive data.
- Source IDs and local metadata remain unencrypted at rest; .state is
  gitignored and owner-only (where supported). Local device access controls
  remain essential.

## Rollback

Do not remove .state if it contains unreviewed work or DB history. For a
pending public promotion, inspect .state/public-promotions/ and the
compile-transactions journal before any manual recovery. The standard
recover_transactions command restores interrupted public files if their bytes
still match recorded before/after contents, otherwise it raises a conflict
instead of overwriting human changes.

## Acceptance

Legacy CLI and released UX-001 unchanged; review-first never automatically
changes the public Wiki or calls git_push; no pi execution without explicit
opt-in; separate manual private acceptance vs public promotion; mutation,
corruption, symlink and crash tests plus full Linux/macOS CI.
