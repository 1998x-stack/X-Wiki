from __future__ import annotations

import os
import sqlite3
import subprocess
import time
from pathlib import Path

import process_voice_memos
import pytest
from compile_wiki import repository_digest, validate_model_changes
from import_voice_memos import RawWriteResult
from process_voice_memos import (
    has_publish_pending,
    knowledge_worktree_dirty,
    legacy_transcript_matches,
    stable_audio_hash,
)


def test_stable_audio_hash_waits_for_young_file(tmp_path: Path) -> None:
    audio = tmp_path / "memo.m4a"
    audio.write_bytes(b"content")
    assert stable_audio_hash(audio, 60) is None
    assert stable_audio_hash(audio, 0) is not None


def test_model_change_boundary_allows_only_wiki_outputs() -> None:
    before = {"README.md": "a", "wiki/topic.md": "a"}
    validate_model_changes(before, {"README.md": "a", "wiki/topic.md": "b", "index.md": "c"})


def test_model_change_boundary_rejects_modified_existing_file() -> None:
    before = {"README.md": "a"}
    try:
        validate_model_changes(before, {"README.md": "b"})
    except RuntimeError as error:
        assert "README.md" in str(error)
    else:
        raise AssertionError("existing out-of-boundary edits must be detected")


def test_dirty_knowledge_detection(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "wiki").mkdir()
    topic = tmp_path / "wiki" / "topic.md"
    topic.write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=tmp_path, check=True)
    topic.write_text(f"changed {time.time()}\n", encoding="utf-8")
    assert knowledge_worktree_dirty(tmp_path)


def test_legacy_model_state_migrates_only_when_language_matches(tmp_path: Path) -> None:
    transcript = tmp_path / "memo.json"
    transcript.write_text('{"language": "zh"}', encoding="utf-8")
    assert legacy_transcript_matches(str(transcript), "model", "model", "zh")
    assert not legacy_transcript_matches(str(transcript), "model", "model", "en")
    assert not legacy_transcript_matches(str(transcript), "old", "model", "zh")


def test_publish_retry_is_explicit_state() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("create table recordings (status text)")
    connection.execute("insert into recordings values ('compiled')")
    assert not has_publish_pending(connection)
    connection.execute("insert into recordings values ('publish_pending')")
    assert has_publish_pending(connection)


def test_stable_audio_hash_missing_file_returns_none(tmp_path: Path) -> None:
    assert stable_audio_hash(tmp_path / "missing.m4a", 0) is None


def test_stable_audio_hash_vanishing_file_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = tmp_path / "memo.m4a"
    audio.write_bytes(b"content")

    def vanish(_: Path) -> str:
        raise FileNotFoundError("deleted while hashing")

    monkeypatch.setattr(process_voice_memos, "sha256_file", vanish)
    assert stable_audio_hash(audio, 0) is None


def test_repository_digest_ignores_cache_and_agent_dirs(tmp_path: Path) -> None:
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "topic.md").write_text("x", encoding="utf-8")
    for cache in (
        ".codegraph",
        ".pytest_cache",
        ".ruff_cache",
        ".omo",
        ".workbuddy-ai",
        "__pycache__",
        ".state",
    ):
        (tmp_path / cache).mkdir(exist_ok=True)
        (tmp_path / cache / "junk.bin").write_bytes(b"junk")
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (tmp_path / ".DS_Store").write_bytes(b"\x00")

    digest = repository_digest(tmp_path)

    assert set(digest) == {"wiki/topic.md"}


def test_transient_compile_timeout_returns_temp_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir()
    (recordings_dir / "memo.m4a").write_bytes(b"audio")
    raw_path = tmp_path / "raw" / "voice" / "2025" / "01" / "memo.md"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_text("evidence", encoding="utf-8")

    recording = {
        "ZUNIQUEID": "ABC123",
        "ZPATH": "memo.m4a",
        "ZDATE": 0.0,
        "ZDURATION": 1.0,
        "ZCUSTOMLABEL": "memo",
    }
    monkeypatch.setattr(process_voice_memos, "discover_recordings", lambda wd: [recording])
    monkeypatch.setattr(process_voice_memos, "stable_audio_hash", lambda p, s: "deadbeef")
    monkeypatch.setattr(
        process_voice_memos, "transcribe", lambda a, m, lang: {"text": "x", "segments": []}
    )
    monkeypatch.setattr(
        process_voice_memos, "write_raw", lambda *a, **k: RawWriteResult(raw_path, True)
    )

    def timeout_compile(*args, **kwargs) -> None:
        raise subprocess.TimeoutExpired("pi", timeout=900)

    monkeypatch.setattr(process_voice_memos, "compile_wiki", timeout_compile)
    monkeypatch.setenv("XWIKI_GIT_PUSH", "false")

    settings = process_voice_memos.Settings.load(tmp_path)
    args = process_voice_memos.build_parser(settings).parse_args(
        ["--recordings-dir", str(recordings_dir)]
    )
    assert process_voice_memos.process(args, settings) == 75

    connection = sqlite3.connect(tmp_path / ".state" / "ingest.sqlite")
    status = connection.execute(
        "select status from recordings where recording_id = ?", ("ABC123",)
    ).fetchone()[0]
    connection.close()
    assert status == "raw_ready"


def test_publish_pending_row_is_recovered_without_retranscription(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A recording left in `publish_pending` by an interrupted push must be
    retried (no-op here) and converge to `compiled`, never re-transcribed."""
    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir()
    (recordings_dir / "memo.m4a").write_bytes(b"audio")
    raw_path = tmp_path / "raw" / "voice" / "2025" / "01" / "memo.md"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_text("evidence", encoding="utf-8")

    recording = {
        "ZUNIQUEID": "ABC123",
        "ZPATH": "memo.m4a",
        "ZDATE": 0.0,
        "ZDURATION": 1.0,
        "ZCUSTOMLABEL": "memo",
    }
    monkeypatch.setattr(process_voice_memos, "discover_recordings", lambda wd: [recording])
    monkeypatch.setattr(process_voice_memos, "stable_audio_hash", lambda p, s: "deadbeef")

    # Re-transcribing a publish_pending row would raise here (fail loudly).
    def no_retranscribe(*_a, **_k) -> None:
        raise AssertionError("publish_pending row must not be re-transcribed")

    monkeypatch.setattr(process_voice_memos, "transcribe", no_retranscribe)
    monkeypatch.setattr(process_voice_memos, "git_publish", lambda *a, **k: None)
    for name in list(os.environ):
        if name.startswith("XWIKI_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XWIKI_GIT_PUSH", "true")

    # Load settings after pinning the environment so git_push is deterministic.
    settings = process_voice_memos.Settings.load(tmp_path)
    fingerprint = process_voice_memos.transcription_fingerprint(
        settings.whisper_model, settings.language
    )
    connection = process_voice_memos.open_state(tmp_path / ".state" / "ingest.sqlite")
    connection.execute(
        "insert into recordings ("
        " recording_id, audio_sha256, audio_path, raw_path, transcript_path, "
        " model, status, updated_at) values (?,?,?,?,?,?,?,?)",
        (
            "ABC123",
            "deadbeef",
            str(recordings_dir / "memo.m4a"),
            str(raw_path),
            None,
            fingerprint,
            "publish_pending",
            "2026-01-01T00:00:00+00:00",
        ),
    )
    connection.commit()

    args = process_voice_memos.build_parser(settings).parse_args(
        ["--recordings-dir", str(recordings_dir)]
    )
    assert process_voice_memos.process(args, settings) == 0
    connection.close()
    status = sqlite3.connect(tmp_path / ".state" / "ingest.sqlite").execute(
        "select status from recordings where recording_id = ?", ("ABC123",)
    ).fetchone()[0]
    assert status == "compiled"
