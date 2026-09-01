#!/usr/bin/env python3
"""Normalize local Apple Voice Memos transcripts into immutable Markdown."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from xwiki_config import Settings

APPLE_EPOCH_OFFSET = 978_307_200
UUID_SUFFIX = re.compile(r"-([0-9A-Fa-f]{8})(?:-[0-9A-Fa-f-]{27})?$")


@dataclass(frozen=True)
class RawWriteResult:
    path: Path
    created: bool


def local_timezone() -> dt.tzinfo:
    timezone_name = os.environ.get("TZ")
    if timezone_name:
        try:
            return ZoneInfo(timezone_name)
        except (KeyError, ValueError):
            pass
    return dt.datetime.now().astimezone().tzinfo or dt.timezone.utc


def apple_time_to_datetime(value: float, timezone: dt.tzinfo | None = None) -> dt.datetime:
    timestamp = value + APPLE_EPOCH_OFFSET
    return dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).astimezone(
        timezone or local_timezone()
    )


def duration_text(seconds: float) -> str:
    seconds_i = max(0, round(seconds))
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


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def load_recordings(db_path: Path) -> list[dict[str, Any]]:
    # Voice Memos commonly keeps current rows in the WAL. The immutable flag
    # would silently ignore that WAL and return stale or empty metadata.
    uri = f"{db_path.expanduser().resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=10) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            select ZDATE, ZDURATION, ZCUSTOMLABEL, ZPATH, ZUNIQUEID
            from ZCLOUDRECORDING
            where lower(ZPATH) like '%.m4a'
            order by ZDATE
            """
        ).fetchall()
    return [dict(row) for row in rows]


def fallback_recordings(recordings_dir: Path) -> list[dict[str, Any]]:
    """Build minimal metadata when Apple's schema is unavailable or changes."""
    recordings: list[dict[str, Any]] = []
    for audio_path in sorted(recordings_dir.glob("*.m4a")):
        try:
            modified_at = audio_path.stat().st_mtime
        except FileNotFoundError:
            continue
        match = UUID_SUFFIX.search(audio_path.stem)
        unique_id = (
            match.group(1).upper()
            if match
            else hashlib.sha256(audio_path.name.encode()).hexdigest()[:16].upper()
        )
        recordings.append(
            {
                "ZDATE": modified_at - APPLE_EPOCH_OFFSET,
                "ZDURATION": 0.0,
                "ZCUSTOMLABEL": audio_path.stem,
                "ZPATH": audio_path.name,
                "ZUNIQUEID": unique_id,
            }
        )
    return recordings


def discover_recordings(recordings_dir: Path) -> list[dict[str, Any]]:
    db_path = recordings_dir / "CloudRecordings.db"
    metadata_error: OSError | sqlite3.DatabaseError | None = None
    if db_path.is_file():
        try:
            return load_recordings(db_path)
        except (OSError, sqlite3.DatabaseError) as error:
            metadata_error = error
            print(f"Voice Memos metadata unavailable ({error}); using file metadata.")
    recordings = fallback_recordings(recordings_dir)
    if not recordings and metadata_error:
        raise RuntimeError(
            "Voice Memos metadata and audio files are inaccessible. "
            "Grant Full Disk Access to the Python executable shown by scripts/doctor.py."
        ) from metadata_error
    return recordings


def format_segment(segment: dict[str, Any]) -> str:
    start = duration_text(float(segment.get("start", 0)))
    text = str(segment.get("text", "")).strip()
    return f"[{start}] {text}"


def yaml_string(value: object) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def markdown_title(value: object) -> str:
    title = " ".join(str(value).splitlines()).strip()
    return title.replace("#", "\\#") or "未命名语音"


def write_raw(
    recording: dict[str, Any],
    recordings_dir: Path,
    transcripts_dir: Path,
    out_root: Path,
    transcript_engine: str = "openai-whisper",
    transcript_model: str = "base",
    timezone: dt.tzinfo | None = None,
) -> RawWriteResult | None:
    audio_path = recordings_dir / str(recording["ZPATH"])
    transcript_json = transcripts_dir / f"{audio_path.stem}.json"
    if not transcript_json.is_file():
        return None

    data = json.loads(transcript_json.read_text(encoding="utf-8"))
    recorded_at = apple_time_to_datetime(float(recording["ZDATE"]), timezone)
    short_id = str(recording["ZUNIQUEID"]).split("-")[0].lower()
    slug = f"{recorded_at.strftime('%Y-%m-%d-%H%M')}-{short_id}"
    out_dir = out_root / "raw" / "voice" / recorded_at.strftime("%Y") / recorded_at.strftime("%m")
    out_path = out_dir / f"{slug}.md"

    segments = data.get("segments") or []
    transcript = "\n\n".join(format_segment(segment) for segment in segments)
    full_text = str(data.get("text", "")).strip()
    language = data.get("language") or "zh"
    audio_hash = sha256_file(audio_path)
    content = f"""---
type: voice_memo
source: apple_voice_memos
recording_id: {yaml_string(recording["ZUNIQUEID"])}
recorded_at: {recorded_at.isoformat()}
duration: {duration_text(float(recording.get("ZDURATION") or 0))}
language: {yaml_string(language)}
transcript_engine: {yaml_string(transcript_engine)}
transcript_model: {yaml_string(transcript_model)}
transcript_confidence: draft
audio_sha256: {audio_hash}
audio_source: {yaml_string(audio_path)}
immutable: true
---

# {markdown_title(recording.get("ZCUSTOMLABEL") or audio_path.stem)}

## Transcript

{transcript}

## Plain Text

{full_text}
"""
    if out_path.exists():
        if out_path.read_text(encoding="utf-8") == content:
            return RawWriteResult(out_path, False)
        revision = hashlib.sha256(content.encode("utf-8")).hexdigest()[:10]
        out_path = out_dir / f"{slug}--rev-{revision}.md"
        if out_path.exists():
            return RawWriteResult(out_path, False)

    atomic_write_text(out_path, content)
    return RawWriteResult(out_path, True)


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    settings = Settings.load(repo)
    parser = argparse.ArgumentParser()
    parser.add_argument("--recordings-dir", type=Path, default=settings.recordings_dir)
    parser.add_argument("--transcripts-dir", type=Path, default=repo / ".state" / "transcripts")
    parser.add_argument("--out-root", type=Path, default=repo)
    parser.add_argument("--transcript-engine", default="mlx-whisper")
    parser.add_argument("--transcript-model", default=settings.whisper_model)
    args = parser.parse_args()

    for recording in discover_recordings(args.recordings_dir.expanduser()):
        result = write_raw(
            recording,
            args.recordings_dir,
            args.transcripts_dir,
            args.out_root,
            args.transcript_engine,
            args.transcript_model,
        )
        if result:
            print(result.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
