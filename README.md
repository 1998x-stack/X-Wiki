# X-Wiki

X-Wiki is a local-first LLM wiki for turning iPhone Voice Memos and other sources into durable Markdown knowledge.

The current setup follows this flow:

```text
iPhone Voice Memos
  -> iCloud sync
  -> Mac local Voice Memos library
  -> local MLX Whisper on Apple Silicon
  -> raw Markdown evidence
  -> pi + iagent/standard + X-Wiki skill
  -> compiled wiki pages
  -> GitHub, GitHub Pages, and GitHub Wiki
```

Start at [index.md](index.md).

## Local Pipeline

The first import used PyTorch Whisper `base` on CPU. The current pipeline uses
`mlx-community/whisper-large-v3-turbo` through MLX on the Apple GPU. No OpenAI
API key is used for transcription.

```bash
python3 -m pip install --user mlx-whisper

python3 scripts/process_voice_memos.py
```

The pipeline keeps idempotent state in `.state/ingest.sqlite`, invokes `pi`
with `iagent/standard` and `skills/x-wiki-compiler`, and pushes compiled changes.

Install the event hook with:

```bash
python3 scripts/install_launch_agent.py
```

The launch agent watches the local Voice Memos directory and also performs a
five-minute recovery scan. Logs are written under `.state/logs/`.

## Publishing

GitHub tracks and publishes only the compiled wiki and automation code.
`raw/voice/`, local state, and transcript caches remain on this Mac and are
excluded from both Git and the rendered site.
