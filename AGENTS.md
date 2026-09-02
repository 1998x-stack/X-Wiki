# X-Wiki Operating Rules

Personal LLM wiki: iPhone Voice Memos → local MLX Whisper → immutable raw evidence → LLM-compiled knowledge layer → GitHub Pages. Only `wiki/`, `index.md`, `log.md`, and site assets leave this machine.

## Layers

- `raw/` is evidence. Never rewrite transcripts for style or interpretation; a changed transcript becomes a new `{slug}--rev-{hash}.md`, never an overwrite. Note the split: `raw/voice/` is gitignored (local-only), `raw/references/` is tracked.
- `wiki/` — compiled knowledge. Pages may be edited, merged, split, cross-linked.
- `scripts/` — all code and its support: Python pipeline modules, `tests/`, the `x-wiki-compiler` skill under `skills/`, and `docs/`. `requirements*.txt` + `pyproject.toml` config live here too.
- `sites/` — publish-layer inputs: `assets/`, `content/` (404), `overrides/` (theme), `requirements-site.txt`. Generated MkDocs input `sites/.site-docs/` and rendered `sites/site/` are gitignored.
- `.state/` — SQLite ingestion state, whisper JSON cache, launchd logs. Gitignored; never the source of truth.

## Editing wiki pages

- Pages and `index.md` use wikilinks `[[wiki/concepts/foo]]`, NOT Markdown links. `[[raw/...]]` links render as a private "local evidence" placeholder on the public site - raw evidence never goes public.
- Keep prose in Chinese (default `XWIKI_LANGUAGE=zh`). Use stable ASCII kebab-case slugs.
- Every material claim needs a `## 来源` section with repo-root-relative links back into `wiki/`.
- Distinguish source facts from interpretation; preserve contradictions as explicit open questions rather than resolving them.
- Update `index.md` only when navigation materially changes; append to `log.md` only when pages were materially edited.

## Pipeline contracts (do not break)

- `scripts/process_voice_memos.py` owns discovery, MLX transcription, idempotent state, compilation, and Git push. `--skip-compile --skip-push` transcribes only; `--reprocess` re-transcribes (generates raw revisions). New recordings wait `XWIKI_MIN_AGE_SECONDS` for stability before hashing.
- Transcription is local `mlx-whisper` only - no OpenAI key, and Apple native-transcript extraction is a planned, not-yet-implemented path.
- `scripts/compile_wiki.py` shells out to `pi` with `scripts/skills/x-wiki-compiler` and `iagent/standard`, restricted to tools `read,write,edit,grep,find,ls`. It verifies `raw/` is byte-identical before/after and that the model touched nothing outside `wiki/`, `index.md`, `log.md`.
- **Credential inheritance for launchd:** the headless compile needs the LLM provider's API key. `install_launch_agent.py` reads provider config from `~/.pi/agent/models.json` and copies each `$VAR` env ref (e.g. `IAUTO_API_KEY`) it finds in the current shell into the launchd plist (`chmod 0600`). Export/authenticate credentials *before* (re)installing; if a referenced env var is unset the installer warns on stderr and headless compilation will be unable to authenticate.
- **Exit code 75 (temporary failure):** the pipeline pauses and retries next scan when knowledge files have uncommitted edits, or when compilation/push fails transiently (pi timeout, Mac asleep mid-run, network blip) — sources stay `raw_ready`/`publish_pending`. Hand-editing `wiki/`, `index.md`, or `log.md` pauses automation until committed.
- Automatic Git commits and pushes stage only `wiki/`, `index.md`, `log.md` to `XWIKI_GIT_REMOTE`/`XWIKI_GIT_BRANCH`. Never stage audio, `.state/`, `raw/voice/`, or the venv - publishing is pipeline-owned and you should never publish from a session yourself. CI (`.github/workflows/quality.yml`) runs `ruff check .` + `pytest` on push to `main` and PRs; `.github/workflows/pages.yml` builds the site from `prepare_site.py` + `mkdocs build --strict`.
- Paths derive from the repo and `Path.home()`; never hardcode a username or Homebrew prefix. Repo-local `.env` overrides defaults (shell env wins; keep secrets out of `.env`). GitHub Pages (via `.github/workflows/pages.yml`) is the only public output - no GitHub Wiki sync.

## Commands

```bash
.venv/bin/python scripts/doctor.py          # preflight; prints the exact Python to grant Full Disk Access
.venv/bin/python scripts/process_voice_memos.py --skip-compile --skip-push
.venv/bin/ruff check .                       # lint; line-length 100, py310 target
.venv/bin/pytest                             # offline (imports scripts/ via conftest; needs only git + tmp dirs)
.venv/bin/python scripts/prepare_site.py && .venv/bin/mkdocs build --strict   # validates all wikilinks

# launchd service com.xwiki.voice-ingest
.venv/bin/python scripts/install_launch_agent.py           # install/refresh (inherits provider $VAR creds; --remove uninstalls, --no-start skips start)
launchctl print gui/$(id -u)/com.xwiki.voice-ingest
tail -n 100 .state/logs/launchd.err.log                    # pipeline stderr
tail -n 100 .state/logs/launchd.out.log                    # pipeline stdout
```

Details: [scripts/docs/configuration.md](scripts/docs/configuration.md) (env vars, permissions, porting) and [scripts/docs/automation.md](scripts/docs/automation.md) (launchd triggers, sleep semantics, failure recovery).
