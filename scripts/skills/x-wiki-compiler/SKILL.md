---
name: x-wiki-compiler
description: Compile new raw voice transcripts and reference notes into the linked X-Wiki knowledge layer. Use when evidence should update durable concepts, entities, projects, decisions, synthesis pages, and the index; do not use for transcription, raw-source cleanup, Git, or publishing.
---

# X-Wiki Compiler

Compile evidence into durable knowledge. A recording is an input, not automatically a permanent page.

## Before Editing

1. Read every source named in the request.
2. Read [references/wiki-schema.md](references/wiki-schema.md).
3. Inspect `index.md`, related `wiki/` pages, and their existing `## 来源` sections.
4. Decide whether each source adds a new claim, strengthens an existing idea, contradicts it, or adds no durable knowledge.

It is valid to make no Wiki edits when existing pages already represent the source accurately. Do not create content merely to demonstrate activity.

## Compile

- Merge recurring ideas into their existing durable page.
- Create a page only when the subject will be useful beyond one source and cannot fit an established page.
- Keep source narrative and timestamps in `raw/`; put interpretations, relationships, decisions, and open questions in `wiki/`.
- Distinguish source claims from interpretation. Preserve contradictions instead of resolving them without evidence.
- Treat low-confidence names, numbers, quotations, and historical details as uncertain. Use neutral wording or record an open question.
- Keep prose concise, concrete, and primarily Chinese. Use stable ASCII file slugs.
- Update `index.md` only when navigation materially changes.
- Append a dated `log.md` entry only when pages were materially edited.

## Boundaries

- Never edit, move, rename, or delete `raw/`.
- Edit only `wiki/`, `index.md`, and `log.md`.
- Never run Git, publish, install dependencies, invoke external services, or change automation configuration.
- The compiled Wiki is published on GitHub Pages. Do not carry credentials, private identifiers, precise addresses, account details, or unnecessary personal specifics from raw evidence into `wiki/`.
- Keep every material claim traceable through a `## 来源` section using repository-root-relative wiki links.
- Do not silently replace a stronger existing formulation with a weaker summary.

## Validate

Before finishing:

1. Confirm no raw file changed.
2. Resolve every new Wiki link or mark the relationship as an open question without creating a broken link.
3. Check that a new page does not duplicate an existing concept under another name.
4. Check that public text reveals no unnecessary private source detail.
5. Report created pages, materially updated pages, no-op decisions, and unresolved uncertainties.
