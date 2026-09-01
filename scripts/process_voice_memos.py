#!/usr/bin/env python3
"""Idempotently transcribe new Voice Memos, compile the wiki, and push Git."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from compile_wiki import compile_wiki
from import_voice_memos import load_recordings, sha256_file, write_raw


DEFAULT_RECORDINGS = Path(
    "/System/Volumes/Data/Users/x/Library/Group Containers/"
    "group.com.apple.VoiceMemos.shared/Recordings"
)
DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"


def json_default(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"cannot serialize {type(value).__name__}")


@contextlib.contextmanager
def exclusive_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another X-Wiki ingestion is already running.")
            raise SystemExit(0)
        yield


def open_state(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
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


def transcribe(audio_path: Path, model: str) -> dict[str, Any]:
    import mlx_whisper

    started = time.monotonic()
    result = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=model,
        language="zh",
        task="transcribe",
        word_timestamps=False,
        condition_on_previous_text=False,
        hallucination_silence_threshold=2.0,
        verbose=False,
    )
    print(f"Transcribed {audio_path.name} in {time.monotonic() - started:.1f}s")
    return result


def save_state(
    connection: sqlite3.Connection,
    recording_id: str,
    audio_hash: str,
    audio_path: Path,
    model: str,
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
            model,
            status,
            error,
            dt.datetime.now(dt.timezone.utc).isoformat(),
        ),
    )
    connection.commit()


def pending_sources(connection: sqlite3.Connection) -> list[Path]:
    rows = connection.execute(
        "select raw_path from recordings where status = 'raw_ready' and raw_path is not null"
    ).fetchall()
    return [Path(row[0]) for row in rows if Path(row[0]).is_file()]


def git_publish(repo: Path) -> None:
    if not (repo / ".git").exists():
        print("Git repository is not initialized; skipping push.")
        return
    subprocess.run(["git", "add", "raw", "wiki", "index.md", "log.md"], cwd=repo, check=True)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo)
    if staged.returncode == 1:
        stamp = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        subprocess.run(["git", "commit", "-m", f"voice: compile {stamp}"], cwd=repo, check=True)
    elif staged.returncode != 0:
        raise subprocess.CalledProcessError(staged.returncode, staged.args)
    subprocess.run(["git", "push", "origin", "main"], cwd=repo, check=True)


def process(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    recordings_dir = args.recordings_dir.resolve()
    db_path = recordings_dir / "CloudRecordings.db"
    if not db_path.is_file():
        raise FileNotFoundError(f"Voice Memos database not found: {db_path}")
    transcript_dir = repo / ".state" / "transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)

    with exclusive_lock(repo / ".state" / "ingest.lock"):
        connection = open_state(repo / ".state" / "ingest.sqlite")
        try:
            for recording in load_recordings(db_path):
                audio_path = recordings_dir / recording["ZPATH"]
                if not audio_path.is_file():
                    continue
                if time.time() - audio_path.stat().st_mtime < args.min_age:
                    print(f"Waiting for file to settle: {audio_path.name}")
                    continue

                recording_id = recording["ZUNIQUEID"]
                audio_hash = sha256_file(audio_path)
                row = connection.execute(
                    "select audio_sha256, model, status from recordings where recording_id = ?",
                    (recording_id,),
                ).fetchone()
                if (
                    not args.all
                    and row
                    and row[0] == audio_hash
                    and row[1] == args.model
                    and row[2] in {"raw_ready", "compiled"}
                ):
                    continue

                try:
                    result = transcribe(audio_path, args.model)
                    transcript_path = transcript_dir / f"{audio_path.stem}.json"
                    transcript_path.write_text(
                        json.dumps(result, ensure_ascii=False, indent=2, default=json_default),
                        encoding="utf-8",
                    )
                    raw_path = write_raw(
                        recording,
                        recordings_dir,
                        transcript_dir,
                        repo,
                        transcript_engine="mlx-whisper",
                        transcript_model=args.model,
                    )
                    if raw_path is None:
                        raise RuntimeError(f"transcript was not imported for {audio_path.name}")
                    save_state(
                        connection,
                        recording_id,
                        audio_hash,
                        audio_path,
                        args.model,
                        "raw_ready",
                        raw_path,
                        transcript_path,
                    )
                except Exception as exc:
                    save_state(
                        connection,
                        recording_id,
                        audio_hash,
                        audio_path,
                        args.model,
                        "failed",
                        error=str(exc),
                    )
                    print(f"Failed to process {audio_path.name}: {exc}", file=sys.stderr)

            sources = pending_sources(connection)
            if sources and not args.skip_compile:
                compile_wiki(repo, sources, args.llm_model, args.provider)
                connection.executemany(
                    "update recordings set status = 'compiled', last_error = null where raw_path = ?",
                    [(str(path),) for path in sources],
                )
                connection.commit()
            if not args.skip_push:
                git_publish(repo)
        finally:
            connection.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--recordings-dir", type=Path, default=DEFAULT_RECORDINGS)
    parser.add_argument("--model", default=os.environ.get("XWIKI_WHISPER_MODEL", DEFAULT_MODEL))
    parser.add_argument("--provider", default="iagent")
    parser.add_argument("--llm-model", default="iagent/standard")
    parser.add_argument("--min-age", type=int, default=30)
    parser.add_argument("--all", action="store_true", help="reprocess recordings already in state")
    parser.add_argument("--skip-compile", action="store_true")
    parser.add_argument("--skip-push", action="store_true")
    return process(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
