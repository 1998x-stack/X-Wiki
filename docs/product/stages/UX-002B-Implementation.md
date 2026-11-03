# UX-002B — Durable Local Transcription Jobs

> Implementation: the local SQLite worker + injected ASR integration, subject to
> GitHub CI; a live Apple Silicon + cached MLX model smoke test is **not** implied
> by a synthetic macOS runner.
>
> Depends on [ARCH-00C](../../architecture/adr-00c-private-public-boundary.md)
> and [UX-002A](UX-002A-Implementation.md).
> Follows the [UX-002 product plan](UX-002-First-Real-Value.md).

## Outcome and privacy

When an audio Source is already durably imported and SHA-256 verified, enqueue
an explicit local transcription task. One worker claims a job; it loads an
**already installed local mlx-whisper model directory**, writes the recognized
Unicode text into its own private immutable blob store, and atomically records
the revision and marks the job `completed`. If killed, it leaves Source bytes
untouched and the job eligible for lease-expiry recovery. Source `stored`
means **original audio persists**, not that its model processing is complete.

The new worker has **no Git, pi, LLM provider, HTTP server or Pages calls**.
The adapter does not take Hugging Face model IDs or automatically download a
model. The user must provision the local model and native dependencies
separately; a third-party native package's network behavior is not a substitute
for an audited OS-level network sandbox.

## Modified and added files

| File | Contract / responsibility |
|---|---|
| `.../migrations/0004_job_leases.sql` | Version 4 migration: model identity, processing lease, retry deadline, attempts and output pointer |
| `.../sqlite/database.py` | Checksum-verified schema version moves 3 → 4; previous SQL is unchanged |
| `.../sqlite/job_repository.py` | Idempotent enqueue, transactional claim, renewal, expiry recovery, sanitized error, retry/cancel, CAS completion |
| `src/xwiki/infrastructure/file_store.py` | Verified private path, audio magic sniffing, immutable text output |
| `src/xwiki/infrastructure/whisper_adapter.py` | Optional MLX Whisper, local-only model directory; lazy import; errors tagged as retryable or terminal |
| `src/xwiki/application/transcription_service.py` | End-to-end one-job execution, independent heartbeat connection, pre/post source verification, result persistence |
| `src/xwiki/interfaces/jobs_cli.py` | Explicit `enqueue`, `run-once`, `status`, `retry`, `cancel`, `recover`, `export-transcript` |
| `tests/integration/jobs/` | Real SQLite+Blob fixtures, crash/restart, concurrent workers, invalid states, corrupt bytes, DB rollback, idempotence |
| `.github/workflows/quality.yml`, `macos-smoke.yml` | Built wheel must include all **four** SQL migration files, unit/integration and browser regression tests |

No modified legacy `recordings` SQLite schema. No automatic bridge from the
old Voice Memos daemon to the new jobs in this PR.

## Local usage

From the repository root:

```sh
pip install -e .
# First import a real audio recording, store its returned source_id:
xwiki-import import /path/to/recording.m4a

# The local model directory must ALREADY exist, with MLX Whisper model files.
xwiki-jobs enqueue <source_id> --model-dir /path/to/local-mlx-whisper-model

# The user intentionally starts ONE processing attempt. A scheduler is not
# started automatically and no remote model is selected.
xwiki-jobs run-once --model-dir /path/to/local-mlx-whisper-model

xwiki-jobs status <job_id>
xwiki-jobs export-transcript <job_id> /path/to/new-transcript.txt
```

Optional `--language zh` must be the **same** on enqueue/run-once because
language is part of the immutable model_key. Passing another model directory
or language selects a different queue identity, not an accidental replay of
the old task.

For errors:

```sh
xwiki-jobs retry <job_id>   # only for an eligible failed_retryable task
xwiki-jobs cancel <job_id>  # terminal; does not delete source bytes
xwiki-jobs recover          # reclaim leases abandoned by dead workers
```

The CLI returns sanitized JSON status, job ID, revision ID and safe error code.
No private filename, source text, model text or traceback is printed on normal
status/error paths. `export-transcript` is a user-initiated explicit file
write that refuses to overwrite a destination.

## Job state machine

```text
queued ──claim+lease──> processing ──verified text + SQLite COMMIT──> completed
                             │
                             ├─retryable error──> failed_retryable
                             │                          │
                             │               retry_after elapsed / manual retry
                             │                          └────> processing
                             │
                             ├─unsupported/corrupt/max attempts─> failed_terminal
                             │
                             └─cancel request─────────────────> cancelled

lease expires after process death: processing → failed_retryable
                                               → failed_terminal if budget exhausted
```

A task identity is deterministic for (source ID, model_key); duplicate enqueue
returns the current job, including its previous attempt count and terminal
status. Up to 3 attempts by default (range 1–10); exponential retry delays
start at 15s and cap at 1h. No infinite retry. A terminal task is not
silently reset: a deliberately changed model version is a new job.

A separate WAL connection renews a live worker's lease. Any completion,
failure or cancellation must pass a current token + unexpired lease check;
a stale worker cannot overwrite a resumed worker's result. Two workers
claim atomically with `BEGIN IMMEDIATE`.

## Integrity and failure semantics

- **Input:** Source must be `stored`; rehash the blob and reject text or
  unsupported magic before creating a transcription job. A migrated
  `queued` legacy placeholder is never treated as verified media.
- **Processing:** Verify audio before invocation and again after it ends;
  output bytes are saved via fsync + atomic rename to a separate private
  TranscriptStore before any SQL completion.
- **Completion:** revision insert, latest Source transcript pointer, job
  completion and attempt history commit in **one SQLite transaction**.
  If the transaction fails, the job stays uncompleted and may recover
  after lease expiry; orphaned private output blobs are harmless.
- **Errors:** platform and malformed transcript failures are terminal.
  Intermittent model/storage errors retry with backoff. Error *codes*, not
  source paths or model exceptions, are persisted.
- **Cancellation:** prevents future SQL commit by revoking the lease,
  but cannot forcibly terminate an already-running native model invocation.
- **Automatic recovery:** an abandoned processing lease can be recovered on
  the next `claim` or via the explicit `recover` command.
- **At-rest:** output blobs stay in a private `.state/transcript-store/`
  directory. No automatic upload, sync or Git publication.

## Boundaries and remaining limitations

- The macOS Actions job runs a **fake transcriber against real local audio
  fixtures and actual SQLite**; it does not prove mlx-whisper or an Apple
  Voice Memos library runs on a physical user's device.
- Format sniffing uses basic WAV/M4A/MP3 header checks, **not** a full decoder;
  real FFmpeg/media probe hardening remains for UX-002C/D.
- Import and job workers remain an explicit Python CLI; there is no
  user-facing daemon/desktop UI and no background scheduler.
- Full consent UI, secure IPC, real Apple Silicon install/test, user
  identity, evidence review and knowledge writeback are not yet delivered.
- The existing `legacy` Voice Memos/Whisper/pi/Git workflow remains
  independently operational and has its prior publishing semantics.

## Acceptance checks

- SQLite schema ledger upgrades to version 4; prior checksummed migrations
  are untouched and `ingest.sqlite` is unchanged.
- Two connections cannot claim a single job; stale tokens cannot finalize.
- Source cannot be lost even when the model, disk, database or process fails.
- Restart recovers expired attempts, preserves history and avoids duplicate
  completed revisions.
- A completed transcript is byte-verifiable and can be explicitly exported.
- Original source `stored` status remains truthful when transcription fails.
- Linux full Quality and synthetic macOS tests including existing UX-001
  browser E2E pass before merging.

## Next: UX-002C

A privileged local bridge will expose typed status, verified output preview,
cancel/retry and privacy controls to a desktop UI; it must never expose a
raw shell/SQLite/file-system endpoint or silently invoke remote inference.
