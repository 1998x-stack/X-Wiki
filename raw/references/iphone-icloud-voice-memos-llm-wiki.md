---
type: research_reference
source: pasted_user_reference
created_at: 2026-09-01T10:13:00+08:00
immutable: true
---

# iPhone, iCloud Voice Memos, and LLM Wiki Architecture

## Key Claims

- iPhone 13 can be used as the lowest-friction capture device: open Voice Memos, record, stop.
- iCloud Voice Memos syncs recordings to the Mac local Voice Memos library.
- The Mac should act as the worker because it can read the local Voice Memos database and audio files.
- Apple native transcripts should be preferred when present, because they avoid extra compute.
- Whisper should be the fallback when Apple transcript extraction is unavailable or empty.
- The LLM wiki should separate immutable raw evidence from mutable compiled knowledge.
- A durable setup should be idempotent, using ingestion state rather than a fragile one-shot file watcher.

## Recommended Pipeline

```text
iPhone 13 Voice Memos
  -> iCloud
  -> Mac local Voice Memos library
  -> Apple transcript extraction
  -> Whisper fallback
  -> raw/voice Markdown
  -> LLM wiki compilation
  -> Git history
```

## Design Commitments

- Capture should be almost zero friction.
- `raw/` should preserve evidence.
- `wiki/` should compile, connect, and revise durable understanding.
- Audio files should remain local or in iCloud/NAS rather than ordinary Git.
- The system should delay processing long enough for iCloud files to become stable.

## Sources Mentioned In Reference

- Apple Voice Memos transcription support.
- Apple Voice Memos iCloud sync documentation.
- Community projects reading `CloudRecordings.db` and `.m4a` transcript atoms.
- Karpathy-style `llm-wiki.md`: raw sources compiled into persistent Markdown knowledge.
- Microsoft `llmwiki`, foundry-works `llm-wiki`, and `obsidian-llm-wiki`.
