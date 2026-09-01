---
name: x-wiki-compiler
description: Compile new raw voice transcripts and reference notes into an existing linked X-Wiki. Use when ingesting sources into this repository's durable concepts, entities, projects, decisions, synthesis pages, and index; do not use for transcription or publishing.
---

# X-Wiki Compiler

Turn newly ingested evidence into durable knowledge without making one permanent summary page per recording.

## Workflow

1. Read the source files named in the request, then inspect related pages under `wiki/` and `index.md`.
2. Read [references/wiki-schema.md](references/wiki-schema.md) before choosing page types or links.
3. Extract claims, recurring ideas, named entities, decisions, contradictions, and open questions.
4. Merge evidence into existing pages when the idea already has a durable home. Create a page only when it will remain useful beyond one source.
5. Update `index.md` when the knowledge map changes and append a concise entry to `log.md`.

## Invariants

- Treat `raw/` as immutable evidence. Never edit, move, rename, or delete it.
- Edit only `wiki/`, `index.md`, and `log.md`.
- Write in Chinese unless a source or established page clearly requires another language.
- Preserve uncertainty. Correct obvious transcription mistakes only in the interpretation layer and do not silently present uncertain names or claims as facts.
- Every material claim added to `wiki/` must remain traceable through a `## 来源` section with repository-relative wiki links.
- Prefer improving a small number of connected pages over generating many shallow pages.
- Do not run Git, publish, install dependencies, or access network services. The calling pipeline owns those side effects.

Finish by reporting which pages were created or materially updated and which questions remain unresolved.
