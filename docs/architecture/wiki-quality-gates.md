# PR-003 — Deterministic Wiki Linter

## Contracts

`python scripts/wiki_lint.py --strict` verifies the public source tree before
site generation, and `python scripts/prepare_site.py --strict` reruns those
checks before creating a publishable site. Both run with the standard library.

### What is enforced

- Every Markdown page in `wiki/<category>/` has a stable kebab-case filename,
  a level-one heading, and a final `## 来源` section with at least one raw source.
- Wiki page type is inferred from its category. **Legacy pages without YAML
  frontmatter remain valid.** When typed frontmatter exists, `type` and
  `title` are required, and explicit IDs must be unique.
- Public wikilinks resolve to actual pages, and tracked
  `raw/references/*.md` paths exist. Untracked `raw/voice/` citations are
  syntactically checked but not required to be present in CI.
- The site builder replaces private evidence wikilinks with non-clickable
  HTML containing only the safe label. Unsafe targets, traversal and
  dangling links fail in strict mode.
- High-confidence secret and private-identifier patterns block publication in public site inputs, `log.md`, and tracked `raw/references/`.
  These heuristics are intentionally not a proof of complete privacy.
- Only known generated output directories can be cleared. Symlinked source
  content and unsafe deletion targets are rejected.
- Fenced code and single-backtick inline code are excluded from wikilink
  processing, so code samples remain unchanged.

### Commands

```bash
python scripts/wiki_lint.py --strict
python scripts/wiki_lint.py --strict --json
python scripts/prepare_site.py --strict
mkdocs build --strict
pytest
ruff check .
```

### Known limitations

- The linter checks links, not the factual correctness of article claims.
- Missing untracked voice source files cannot be verified on GitHub CI.
- The privacy scanner uses high-confidence patterns and cannot replace
  human review, LLM-provider controls or scoped public-content approvals.
- The frontmatter parser supports scalar metadata; complex YAML should be
  added only alongside an explicit schema migration.
- `git_publish()` enforces the same source lint **before committing or pushing**\n  generated content. GitHub Pages additionally checks the content before deployment.\n  Existing public Git history is outside the scope of these guards.
