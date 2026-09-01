#!/usr/bin/env python3
"""Idempotently transcribe new Voice Memos, compile the wiki, and push Git."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import sqlite3
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from compile_wiki import compile_wiki
from import_voice_memos import (
    atomic_write_text,
    discover_recordings,
    sha256_file,
    write_raw,
)
from xwiki_config import Settings

TEMPORARY_FAILURE = 75


def json_default(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"cannot serialize {type(value).__name__}")


@contextlib.contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another X-Wiki ingestion is already running.")
            raise SystemExit(0) from None
        yield


def open_state(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.execute("pragma journal_mode = wal")
    connection.execute("pragma busy_timeout = 30000")
    connection.execute(
        """
        create table if not exists recordings (
            recording_id text primary key,
            audio_sha256 text not null,
            audio_path text not null,
            raw_path text,
            transcript_path text,
            model text not null,
            status text not null,
            last_error text,
            updated_at text not null
        )
        """
    )
    connection.commit()
    return connection


def transcription_fingerprint(model: str, language: str) -> str:
    return f"{model}|{language}|no-context|hallucination-silence-2.0"


def legacy_transcript_matches(
    transcript_path: str | None,
    state_model: str,
    requested_model: str,
    requested_language: str,
) -> bool:
    if state_model != requested_model or not transcript_path:
        return False
    try:
        data = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return data.get("language") == requested_language


def transcribe(audio_path: Path, model: str, language: str) -> dict[str, Any]:
    import mlx_whisper

    started = time.monotonic()
    result = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=model,
        language=language,
        task="transcribe",
        word_timestamps=False,
        condition_on_previous_text=False,
        hallucination_silence_threshold=2.0,
        verbose=False,
    )
    print(f"Transcribed {audio_path.name} in {time.monotonic() - started:.1f}s")
    return result


def stable_audio_hash(audio_path: Path, min_age_seconds: int) -> str | None:
    """Hash an audio file only after it has been untouched long enough.

    Returns None (skip until the next scan) when the file is still settling,
    missing, or changed while hashing. A recording deleted or replaced mid-scan
    must never crash the whole run.
    """
    try:
        before = audio_path.stat()
    except OSError as error:
        print(f"Skipping unavailable recording: {audio_path.name} ({error})")
        return None
    if time.time() - before.st_mtime < min_age_seconds:
        print(f"Waiting for file to settle: {audio_path.name}")
        return None
    try:
        digest = sha256_file(audio_path)
        after = audio_path.stat()
    except OSError as error:
        print(
            f"Recording changed or vanished while hashing; retrying later: "
            f"{audio_path.name} ({error})"
        )
        return None
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        print(f"File changed while hashing; retrying later: {audio_path.name}")
        return None
    return digest


def save_state(
    connection: sqlite3.Connection,
    recording_id: str,
    audio_hash: str,
    audio_path: Path,
    model_fingerprint: str,
    status: str,
    raw_path: Path | None = None,
    transcript_path: Path | None = None,
    error: str | None = None,
) -> None:
    connection.execute(
        """
        insert into recordings (
            recording_id, audio_sha256, audio_path, raw_path,
            transcript_path, model, status, last_error, updated_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(recording_id) do update set
            audio_sha256=excluded.audio_sha256,
            audio_path=excluded.audio_path,
            raw_path=coalesce(excluded.raw_path, recordings.raw_path),
            transcript_path=coalesce(excluded.transcript_path, recordings.transcript_path),
            model=excluded.model,
            status=excluded.status,
            last_error=excluded.last_error,
            updated_at=excluded.updated_at
        """,
        (
            recording_id,
            audio_hash,
            str(audio_path),
            str(raw_path) if raw_path else None,
            str(transcript_path) if transcript_path else None,
            model_fingerprint,
            status,
            error,
            dt.datetime.now(dt.timezone.utc).isoformat(),
        ),
    )
    connection.commit()


def pending_sources(connection: sqlite3.Connection) -> list[Path]:
    rows = connection.execute(
        """
        select distinct raw_path
        from recordings
        where status = 'raw_ready' and raw_path is not null
        """
    ).fetchall()
    return sorted(Path(row[0]) for row in rows if Path(row[0]).is_file())


def has_publish_pending(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "select 1 from recordings where status = 'publish_pending' limit 1"
    ).fetchone()
    return row is not None


def knowledge_worktree_dirty(repo: Path) -> list[str]:
    if not (repo / ".git").is_dir():
        return []
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", "wiki", "index.md", "log.md"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def git_publish(repo: Path, remote: str, branch: str) -> None:
    if not (repo / ".git").is_dir():
        print("Git repository is not initialized; skipping push.")
        return
    remote_check = subprocess.run(
        ["git", "remote", "get-url", remote],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if remote_check.returncode != 0:
        print(f"Git remote {remote!r} is not configured; skipping push.")
        return

    subprocess.run(["git", "add", "wiki", "index.md", "log.md"], cwd=repo, check=True)
    knowledge_paths = ["wiki", "index.md", "log.md"]
    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet", "--", *knowledge_paths], cwd=repo
    )
    if staged.returncode == 1:
        stamp = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        subprocess.run(
            ["git", "commit", "--only", "-m", f"voice: compile {stamp}", "--", *knowledge_paths],
            cwd=repo,
            check=True,
        )
    elif staged.returncode != 0:
        raise subprocess.CalledProcessError(staged.returncode, staged.args)
    subprocess.run(["git", "push", remote, f"HEAD:{branch}"], cwd=repo, check=True)


def process(args: argparse.Namespace, settings: Settings) -> int:
    repo = args.repo.expanduser().resolve()
    recordings_dir = args.recordings_dir.expanduser()
    if not recordings_dir.is_dir():
        raise FileNotFoundError(
            f"Voice Memos directory is unavailable: {recordings_dir}. "
            "Check XWIKI_RECORDINGS_DIR and Full Disk Access."
        )
    transcript_dir = repo / ".state" / "transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)
    model_fingerprint = transcription_fingerprint(args.model, args.language)
    failures = 0

    with exclusive_lock(repo / ".state" / "ingest.lock"):
        connection = open_state(repo / ".state" / "ingest.sqlite")
        try:
            recordings = discover_recordings(recordings_dir)
            print(f"Discovered {len(recordings)} recording(s).")
            for recording in recordings:
                audio_path = recordings_dir / str(recording["ZPATH"])
                if not audio_path.is_file():
                    continue
                recording_id = str(recording["ZUNIQUEID"])
                audio_hash = stable_audio_hash(audio_path, args.min_age)
                if audio_hash is None:
                    continue
                row = connection.execute(
                    """
                    select audio_sha256, model, status, transcript_path
                    from recordings
                    where recording_id = ?
                    """,
                    (recording_id,),
                ).fetchone()
                legacy_match = bool(
                    row and legacy_transcript_matches(row[3], row[1], args.model, args.language)
                )
                if (
                    not args.reprocess
                    and row
                    and row[0] == audio_hash
                    and (row[1] == model_fingerprint or legacy_match)
                    and row[2] in {"raw_ready", "compiled"}
                ):
                    if legacy_match:
                        connection.execute(
                            "update recordings set model = ? where recording_id = ?",
                            (model_fingerprint, recording_id),
                        )
                        connection.commit()
                    continue

                try:
                    result = transcribe(audio_path, args.model, args.language)
                    transcript_path = transcript_dir / f"{audio_path.stem}.json"
                    atomic_write_text(
                        transcript_path,
                        json.dumps(result, ensure_ascii=False, indent=2, default=json_default),
                    )
                    raw_result = write_raw(
                        recording,
                        recordings_dir,
                        transcript_dir,
                        repo,
                        transcript_engine="mlx-whisper",
                        transcript_model=args.model,
                    )
                    if raw_result is None:
                        raise RuntimeError(f"transcript was not imported for {audio_path.name}")
                    save_state(
                        connection,
                        recording_id,
                        audio_hash,
                        audio_path,
                        model_fingerprint,
                        "raw_ready",
                        raw_result.path,
                        transcript_path,
                    )
                except Exception as error:  # Continue so one corrupt memo cannot block the queue.
                    failures += 1
                    save_state(
                        connection,
                        recording_id,
                        audio_hash,
                        audio_path,
                        model_fingerprint,
                        "failed",
                        error=str(error),
                    )
                    print(f"Failed to process {audio_path.name}: {error}", file=sys.stderr)

            sources = pending_sources(connection)
            if sources and not args.skip_compile:
                dirty = knowledge_worktree_dirty(repo)
                if dirty:
                    print(
                        "Wiki compilation paused because knowledge files have uncommitted edits:\n"
                        + "\n".join(dirty),
                        file=sys.stderr,
                    )
                    return TEMPORARY_FAILURE
                try:
                    compile_wiki(
                        repo,
                        sources,
                        args.llm_model,
                        args.provider,
                        pi_bin=settings.pi_bin,
                        timeout_seconds=settings.compile_timeout_seconds,
                    )
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
                    # Compilation is a single wall-clock call; a Mac that falls
                    # asleep mid-run or a flaky pi invocation fails transiently.
                    # Keep sources raw_ready and retry on the next scan.
                    print(
                        f"Compilation failed transiently ({error}); retrying on next scan.",
                        file=sys.stderr,
                    )
                    return TEMPORARY_FAILURE
                next_status = (
                    "publish_pending" if settings.git_push and not args.skip_push else "compiled"
                )
                connection.executemany(
                    """
                    update recordings
                    set status = ?, last_error = null
                    where raw_path = ?
                    """,
                    [(next_status, str(path)) for path in sources],
                )
                connection.commit()
            if not args.skip_push and settings.git_push and has_publish_pending(connection):
                try:
                    git_publish(repo, settings.git_remote, settings.git_branch)
                except (subprocess.CalledProcessError, OSError) as error:
                    # Keep publish_pending so the push is retried next scan.
                    print(
                        f"Publish failed transiently ({error}); publish_pending kept for retry.",
                        file=sys.stderr,
                    )
                    return TEMPORARY_FAILURE
                connection.execute(
                    """
                    update recordings
                    set status = 'compiled', last_error = null
                    where status = 'publish_pending'
                    """
                )
                connection.commit()
        finally:
            connection.close()
    return 1 if failures else 0


def build_parser(settings: Settings) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=settings.repo)
    parser.add_argument("--recordings-dir", type=Path, default=settings.recordings_dir)
    parser.add_argument("--model", default=settings.whisper_model)
    parser.add_argument("--language", default=settings.language)
    parser.add_argument("--provider", default=settings.llm_provider)
    parser.add_argument("--llm-model", default=settings.llm_model)
    parser.add_argument("--min-age", type=int, default=settings.min_age_seconds)
    parser.add_argument("--reprocess", "--all", action="store_true")
    parser.add_argument("--skip-compile", action="store_true")
    parser.add_argument("--skip-push", action="store_true")
    return parser


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    settings = Settings.load(repo)
    return process(build_parser(settings).parse_args(), settings)


if __name__ == "__main__":
    raise SystemExit(main())
