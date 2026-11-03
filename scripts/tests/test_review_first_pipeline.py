"""ARCH-00C regression: review-first never triggers legacy automatic publication."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import process_voice_memos
import pytest
from import_voice_memos import RawWriteResult
from process_voice_memos import open_state
from xwiki_config import Settings


def settings_for(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str) -> Settings:
    for key in tuple(os.environ):
        if key.startswith("XWIKI_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("XWIKI_PIPELINE_MODE", mode)
    monkeypatch.setenv("XWIKI_GIT_PUSH", "true")
    return Settings.load(tmp_path)


def prepare_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    recordings = tmp_path / "recordings"
    recordings.mkdir()
    (recordings / "memo.m4a").write_bytes(b"synthetic audio")
    raw = tmp_path / "raw" / "voice" / "memo.md"
    raw.parent.mkdir(parents=True)
    raw.write_text("# Synthetic private evidence\n", encoding="utf-8")
    memo = {
        "ZUNIQUEID": "MEMO-123",
        "ZPATH": "memo.m4a",
        "ZDATE": 0.0,
        "ZDURATION": 1.0,
        "ZCUSTOMLABEL": "Synthetic recording",
    }
    monkeypatch.setattr(process_voice_memos, "discover_recordings", lambda _path: [memo])
    monkeypatch.setattr(process_voice_memos, "stable_audio_hash", lambda *_: "a" * 64)
    monkeypatch.setattr(
        process_voice_memos,
        "transcribe",
        lambda *_: {"text": "synthetic", "segments": []},
    )
    monkeypatch.setattr(
        process_voice_memos,
        "write_raw",
        lambda *args, **kwargs: RawWriteResult(raw, True),
    )
    return recordings


def _run(tmp_path: Path, recordings: Path, settings: Settings) -> int:
    args = process_voice_memos.build_parser(settings).parse_args(
        ["--repo", str(tmp_path), "--recordings-dir", str(recordings)]
    )
    return process_voice_memos.process(args, settings)


def status(tmp_path: Path) -> str:
    connection = sqlite3.connect(tmp_path / ".state" / "ingest.sqlite")
    try:
        return connection.execute(
            "SELECT status FROM recordings WHERE recording_id='MEMO-123'"
        ).fetchone()[0]
    finally:
        connection.close()


@pytest.mark.parametrize(
    "candidate,expected_status",
    [("d" * 64, "proposal_pending"), (None, "reviewed_no_change")],
)
def test_review_first_records_private_outcome_without_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, candidate: str | None, expected_status: str
) -> None:
    recordings = prepare_input(tmp_path, monkeypatch)
    settings = settings_for(tmp_path, monkeypatch, "review_first")
    called: list[dict[str, object]] = []

    def fake_compile(*_args: object, **kwargs: object) -> str | None:
        called.append(kwargs)
        return candidate

    monkeypatch.setattr(process_voice_memos, "compile_wiki", fake_compile)
    monkeypatch.setattr(
        process_voice_memos,
        "git_publish",
        lambda *_args: pytest.fail("review_first must never publish automatically"),
    )
    assert _run(tmp_path, recordings, settings) == 0
    assert status(tmp_path) == expected_status
    assert len(called) == 1
    assert called[0]["mode"] == "review_first"
    assert called[0]["external_processing_approved"] is False
    assert _run(tmp_path, recordings, settings) == 0
    assert len(called) == 1, "never recompile completed private proposal"


def test_review_first_fails_closed_without_model_egress_consent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recordings = prepare_input(tmp_path, monkeypatch)
    settings = settings_for(tmp_path, monkeypatch, "review_first")

    def denied(*_args: object, **kwargs: object) -> None:
        assert kwargs["external_processing_approved"] is False
        raise PermissionError("model egress not approved")

    monkeypatch.setattr(process_voice_memos, "compile_wiki", denied)
    monkeypatch.setattr(
        process_voice_memos,
        "git_publish",
        lambda *_: pytest.fail("denied compilation must never publish"),
    )
    assert _run(tmp_path, recordings, settings) == 75
    assert status(tmp_path) == "raw_ready"


def test_review_first_ignores_legacy_publish_pending_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recordings = prepare_input(tmp_path, monkeypatch)
    settings = settings_for(tmp_path, monkeypatch, "review_first")
    with open_state(tmp_path / ".state" / "ingest.sqlite") as db:
        db.execute(
            """INSERT INTO recordings
             (recording_id,audio_sha256,audio_path,raw_path,transcript_path,
              model,status,updated_at)
             VALUES (?,?,?,?,?,?,?,?)""",
            (
                "MEMO-123",
                "a" * 64,
                str(recordings / "memo.m4a"),
                None,
                None,
                process_voice_memos.transcription_fingerprint(
                    settings.whisper_model, settings.language
                ),
                "publish_pending",
                "2026-11-03T00:00:00Z",
            ),
        )
    monkeypatch.setattr(
        process_voice_memos, "git_publish", lambda *_: pytest.fail("no legacy push")
    )
    monkeypatch.setattr(
        process_voice_memos, "transcribe", lambda *_: pytest.fail("no retranscription")
    )
    assert _run(tmp_path, recordings, settings) == 0
    assert status(tmp_path) == "publish_pending"


def test_legacy_still_calls_original_compile_signature(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recordings = prepare_input(tmp_path, monkeypatch)
    settings = settings_for(tmp_path, monkeypatch, "legacy")
    called: list[dict[str, object]] = []

    def fake_compile(*_args: object, **kwargs: object) -> None:
        called.append(kwargs)
        return None

    monkeypatch.setattr(process_voice_memos, "compile_wiki", fake_compile)
    monkeypatch.setattr(
        process_voice_memos,
        "git_publish",
        lambda *_: process_voice_memos.PublishResult("abc", "origin", "main"),
    )
    assert _run(tmp_path, recordings, settings) == 0
    assert len(called) == 1
    assert "mode" not in called[0]
    assert status(tmp_path) == "compiled"


@pytest.mark.parametrize("bad", ["unknown", "Legacy!", "publish"])
def test_unknown_pipeline_mode_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    monkeypatch.setenv("XWIKI_PIPELINE_MODE", bad)
    with pytest.raises(ValueError, match="XWIKI_PIPELINE_MODE"):
        Settings.load(tmp_path)
