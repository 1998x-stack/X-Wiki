# PR-005 — Deployment read-back and automatic knowledge navigation

## Why Git and website publication are distinct

A successful Git push says only that the remote branch accepted a commit.
A green `deploy-pages` step says the GitHub Pages deployment API completed.
Neither by itself proves the HTTP endpoint serves that commit.

The publishing workflow therefore performs an independent HTTPS GET after
`deploy-pages`. It fetches `release-manifest.json` from the configured public
site, adds a commit-specific cache-busting query string, and compares:

- the exact 40-character Git commit SHA,
- the content SHA-256,
- manifest version, and
- every public file path and Git blob SHA.

Only exact equality produces `deployment-receipt.json`, stored as a GitHub
Actions artifact with a 90-day retention policy. The read-back retries for up
to 180 seconds to accommodate CDN propagation; a failure makes the deploy job
red rather than claiming website verification.

The read-back request enforces HTTPS, configured hostname and website path,
rejects redirects to a different origin, and caps the response at 1 MB.
No private Voice Memo data, provider tokens, or local file paths enter the
receipt. The HTTP receipt is **not** a permanent record; downstream systems
requiring long-lived audit history should store it in durable storage.

## Navigation

`scripts/mkdocs_nav.py` is a MkDocs configuration hook. It reads each page
from the prepared public `sites/.site-docs/wiki/` tree, derives a display
title from the first Markdown H1, and adds the page to the appropriate
section: 综合, 概念, 人物, 决策, 项目. It fails if a Markdown knowledge page
is not included. Adding a new knowledge page no longer requires manually
editing `mkdocs.yml`.

## Validation

- `pytest scripts/tests/test_verify_deployment.py scripts/tests/test_mkdocs_nav.py`
- `pytest` and `ruff check .`
- `python scripts/prepare_site.py --strict && mkdocs build --strict`
- GitHub Pages workflow read-back after deployment
- macOS synthetic pipeline smoke checks (no access to private local audio)

## Limits

Live MLX Whisper, iCloud Voice Memos metadata, and actual pi provider calls
must still be tested on an authorized Apple Silicon Mac. The macOS CI runs
synthetic repository tests only and should not be described as that E2E.
