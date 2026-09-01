#!/usr/bin/env python3
"""Import local Apple Voice Memos transcripts into raw Markdown sources.

This script is read-only against the Apple Voice Memos library. It expects
Whisper JSON files to already exist and writes Markdown evidence files under
raw/voice/YYYY/MM/.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sqlite3
from pathlib import Path


APPLE_EPOCH_OFFSET = 978_307_200
LOCAL_TZ = dt.timezone(dt.timedelta(hours=8))


def apple_time_to_iso(value: float) -> str:
    timestamp = value + APPLE_EPOCH_OFFSET
    return dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).astimezone(LOCAL_TZ).isoformat()


def duration_text(seconds: float) -> str:
    seconds_i = int(round(seconds))
    minutes, second = divmod(seconds_i, 60)
    hour, minute = divmod(minutes, 60)
    if hour:
        return f"{hour:02d}:{minute:02d}:{second:02d}"
    return f"{minute:02d}:{second:02d}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_recordings(db_path: Path) -> list[dict]:
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            select ZDATE, ZDURATION, ZCUSTOMLABEL, ZPATH, ZUNIQUEID
            from ZCLOUDRECORDING
            where ZPATH like '%.m4a'
            order by ZDATE
            """
        ).fetchall()
    return [dict(row) for row in rows]


def format_segment(segment: dict) -> str:
    start = duration_text(float(segment.get("start", 0)))
    text = str(segment.get("text", "")).strip()
    return f"[{start}] {text}"


def write_raw(
    recording: dict,
    recordings_dir: Path,
    transcripts_dir: Path,
    out_root: Path,
    transcript_engine: str = "openai-whisper",
    transcript_model: str = "base",
) -> Path | None:
    audio_path = recordings_dir / recording["ZPATH"]
    stem = audio_path.stem
    transcript_json = transcripts_dir / f"{stem}.json"
    if not transcript_json.exists():
        return None

    data = json.loads(transcript_json.read_text(encoding="utf-8"))
    recorded_at = dt.datetime.fromisoformat(apple_time_to_iso(recording["ZDATE"]))
    year = recorded_at.strftime("%Y")
    month = recorded_at.strftime("%m")
    short_id = recording["ZUNIQUEID"].split("-")[0]
    slug = f"{recorded_at.strftime('%Y-%m-%d-%H%M')}-{short_id.lower()}"
    out_dir = out_root / "raw" / "voice" / year / month
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slug}.md"

    segments = data.get("segments", [])
    transcript = "\n\n".join(format_segment(segment) for segment in segments)
    full_text = str(data.get("text", "")).strip()
    title = stem
    language = data.get("language") or "zh"

    content = f"""---
type: voice_memo
source: apple_voice_memos
recording_id: {recording["ZUNIQUEID"]}
recorded_at: {recorded_at.isoformat()}
duration: {duration_text(float(recording["ZDURATION"]))}
language: {language}
transcript_engine: {transcript_engine}
transcript_model: {transcript_model}
transcript_confidence: draft
audio_sha256: {sha256_file(audio_path)}
audio_source: {audio_path}
immutable: true
---

# {title}

## Transcript

{transcript}

## Plain Text

{full_text}
"""
    out_path.write_text(content, encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--recordings-dir",
        default="/System/Volumes/Data/Users/x/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings",
    )
    parser.add_argument(
        "--transcripts-dir",
        default="/Users/x/Desktop/X-Wiki/.workbuddy-ai/transcripts",
    )
    parser.add_argument("--out-root", default="/Users/x/Desktop/X-Wiki")
    parser.add_argument("--transcript-engine", default="openai-whisper")
    parser.add_argument("--transcript-model", default="base")
    args = parser.parse_args()

    recordings_dir = Path(args.recordings_dir)
    db_path = recordings_dir / "CloudRecordings.db"
    transcripts_dir = Path(args.transcripts_dir)
    out_root = Path(args.out_root)

    written = []
    for recording in load_recordings(db_path):
        out_path = write_raw(
            recording,
            recordings_dir,
            transcripts_dir,
            out_root,
            args.transcript_engine,
            args.transcript_model,
        )
        if out_path:
            written.append(out_path)

    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
