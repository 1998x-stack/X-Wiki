# X-Wiki Schema

## Layers

- `raw/voice/YYYY/MM/`: immutable transcripts and recording metadata.
- `raw/references/`: immutable external or architectural source notes.
- `wiki/concepts/`: reusable mental models and ideas.
- `wiki/entities/`: people, organizations, works, places, and named systems.
- `wiki/projects/`: active bodies of work with outcomes and next actions.
- `wiki/decisions/`: durable decisions, rationale, consequences, and revisit conditions.
- `wiki/synthesis/`: cross-source essays that connect several concepts.

## Linking

Use repository-root-relative wiki links without a file extension:

```markdown
[[wiki/concepts/example|Readable label]]
[[raw/voice/2025/02/source-id|Source recording]]
```

Every compiled page ends with `## 来源`. Add a source only when it supports content on that page.

## Compilation Decisions

- Update an existing page when the source sharpens, supports, challenges, or extends its core idea.
- Create a concept when the idea can recur across contexts.
- Create an entity only when tracking that entity improves retrieval or relationships.
- Create a synthesis only when at least two sources or concepts gain meaning from being connected.
- Keep source-specific chronology in raw evidence unless it is itself a reusable project or decision record.

## Quality Check

Before finishing, verify that no raw file changed, new links resolve, duplicate concepts were not introduced, interpretation is distinguishable from source claims, and the index exposes genuinely important new pages.
