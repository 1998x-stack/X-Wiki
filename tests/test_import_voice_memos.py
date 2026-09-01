from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from import_voice_memos import (
    APPLE_EPOCH_OFFSET,
    RawWriteResult,
    apple_time_to_datetime,
    discover_recordings,
    duration_text,
    write_raw,
)


def test_duration_and_apple_timestamp_boundaries() -> None:
    assert duration_text(-1) == "00:00"
    assert duration_text(59.6) == "01:00"
    assert duration_text(3661) == "01:01:01"
    value = 1_700_000_000 - APPLE_EPOCH_OFFSET
    converted = apple_time_to_datetime(value, dt.timezone.utc)
    assert converted == dt.datetime.fromtimestamp(1_700_000_000, tz=dt.timezone.utc)


def test_discovery_falls_back_to_audio_metadata(tmp_path: Path) -> None:
    audio = tmp_path / "20260901-ABCDEF12-0000-0000-0000-000000000000.m4a"
    audio.write_bytes(b"audio")

    recordings = discover_recordings(tmp_path)

    assert recordings[0]["ZPATH"] == audio.name
    assert recordings[0]["ZUNIQUEID"] == "ABCDEF12"


def test_raw_is_immutable_and_changes_create_revision(tmp_path: Path) -> None:
    recordings = tmp_path / "recordings"
    transcripts = tmp_path / "transcripts"
    recordings.mkdir()
    transcripts.mkdir()
    audio = recordings / "memo.m4a"
    audio.write_bytes(b"audio")
    transcript = transcripts / "memo.json"
    transcript.write_text(
        json.dumps(
            {
                "language": "zh",
                "text": "第一版",
                "segments": [{"start": 0, "text": "第一版"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    recording = {
        "ZDATE": 0,
        "ZDURATION": 1,
        "ZCUSTOMLABEL": "标题\n#注入",
        "ZPATH": audio.name,
        "ZUNIQUEID": "ABCDEF12-0000",
    }

    first = write_raw(recording, recordings, transcripts, tmp_path, timezone=dt.timezone.utc)
    assert isinstance(first, RawWriteResult)
    assert first.created
    original = first.path.read_text(encoding="utf-8")
    assert "# 标题 \\#注入" in original

    same = write_raw(recording, recordings, transcripts, tmp_path, timezone=dt.timezone.utc)
    assert same == RawWriteResult(first.path, False)

    transcript.write_text(
        json.dumps({"language": "zh", "text": "第二版", "segments": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    revision = write_raw(recording, recordings, transcripts, tmp_path, timezone=dt.timezone.utc)
    assert isinstance(revision, RawWriteResult)
    assert revision.created
    assert "--rev-" in revision.path.name
    assert first.path.read_text(encoding="utf-8") == original


def test_missing_transcript_is_a_noop(tmp_path: Path) -> None:
    recording = {
        "ZDATE": 0,
        "ZDURATION": 0,
        "ZCUSTOMLABEL": "missing",
        "ZPATH": "missing.m4a",
        "ZUNIQUEID": "ABC",
    }
    result = write_raw(recording, tmp_path, tmp_path, tmp_path)
    assert result is None


def test_inaccessible_database_without_audio_has_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "CloudRecordings.db").write_bytes(b"not-sqlite")
    monkeypatch.setattr("import_voice_memos.fallback_recordings", lambda _: [])
    with pytest.raises(RuntimeError, match="Full Disk Access"):
        discover_recordings(tmp_path)
