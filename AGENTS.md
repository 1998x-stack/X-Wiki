# X-Wiki Operating Rules

This repository is a personal LLM wiki built from local sources.

## Layers

- `raw/` is evidence. Do not rewrite raw transcripts for style or interpretation. If a transcript is improved, add a new version or update metadata deliberately.
- `wiki/` is compiled knowledge. Pages here may be edited, merged, split, and cross-linked as understanding improves.
- `.state/` is for idempotent ingestion state and should not become the source of truth.

## Voice Memo Pipeline

1. Discover Apple Voice Memos from the local macOS library.
2. Prefer Apple native transcripts if they are present in the audio/container.
3. Fall back to local MLX Whisper when Apple transcript is missing.
4. Write normalized Markdown into `raw/voice/YYYY/MM/`.
5. Compile durable ideas into `wiki/concepts/`, `wiki/entities/`, `wiki/projects/`, `wiki/decisions/`, and `wiki/synthesis/`.

## Compilation Style

- Preserve evidence links from wiki pages back to raw source files.
- Distinguish transcript facts from interpretation.
- Merge repeated ideas into durable concept pages instead of creating isolated summaries.
- Track open questions and contradictions explicitly.

## Automation

- `scripts/process_voice_memos.py` owns discovery, MLX transcription, idempotent state, compilation, and Git push.
- `scripts/compile_wiki.py` must load `skills/x-wiki-compiler` through `pi` using `iagent/standard`.
- The compiler may edit only `wiki/`, `index.md`, and `log.md`; publishing remains outside the model process.
