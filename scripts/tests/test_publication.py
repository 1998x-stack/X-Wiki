"""Regression tests for publication correctness and crash recovery."""

from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import process_voice_memos
import pytest
from process_voice_memos import PublishResult, git_publish


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, text=True, capture_output=True
    ).stdout.strip()


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "X-Wiki Test")
    git(repo, "config", "user.email", "xwiki@example.invalid")
    (repo / "wiki").mkdir()
    (repo / "wiki" / "concept.md").write_text("first\n", encoding="utf-8")
    (repo / "index.md").write_text("# Index\n", encoding="utf-8")
    (repo / "log.md").write_text("# Log\n", encoding="utf-8")
    git(repo, "add", "wiki", "index.md", "log.md")
    git(repo, "commit", "-m", "initial")
    return repo


def test_git_publish_without_repository_is_failure(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="not initialized"):
        git_publish(tmp_path, "origin", "main")


def test_git_publish_without_remote_is_failure(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    with pytest.raises(RuntimeError, match="not configured"):
        git_publish(repo, "origin", "main")


def test_git_publish_returns_confirmed_remote_commit(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    remote = tmp_path / "remote.git"
    git(repo, "init", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    (repo / "wiki" / "concept.md").write_text("updated\n", encoding="utf-8")

    result = git_publish(repo, "origin", "main")
    assert isinstance(result, PublishResult)
    assert result.remote == "origin" and result.branch == "main"
    assert result.commit_sha == git(repo, "rev-parse", "HEAD")
    assert result.commit_sha == git(repo, "ls-remote", "origin", "refs/heads/main").split()[0]

    # Crash after push, before DB update: retry must be idempotent.
    assert git_publish(repo, "origin", "main").commit_sha == result.commit_sha


def test_git_publish_remote_rejection_is_failure(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    git(repo, "remote", "add", "origin", str(tmp_path / "does-not-exist.git"))
    with pytest.raises(subprocess.CalledProcessError):
        git_publish(repo, "origin", "main")


def test_failed_publish_retains_pending_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recordings = tmp_path / "recordings"
    recordings.mkdir()
    audio = recordings / "memo.m4a"
    audio.write_bytes(b"audio")
    raw = tmp_path / "raw" / "voice" / "memo.md"
    raw.parent.mkdir(parents=True)
    raw.write_text("evidence\n", encoding="utf-8")
    monkeypatch.setattr(process_voice_memos, "discover_recordings", lambda _: [
        {"ZUNIQUEID": "id", "ZPATH": audio.name}
    ])
    monkeypatch.setattr(process_voice_memos, "stable_audio_hash", lambda *_: "hash")
    monkeypatch.setattr(process_voice_memos, "git_publish", lambda *_: (
        (_ for _ in ()).throw(RuntimeError("remote missing"))
    ))
    monkeypatch.setenv("XWIKI_GIT_PUSH", "true")
    settings = process_voice_memos.Settings.load(tmp_path)
    db = process_voice_memos.open_state(tmp_path / ".state" / "ingest.sqlite")
    db.execute(
        """insert into recordings
        (recording_id, audio_sha256, audio_path, raw_path, model, status, updated_at)
        values (?, ?, ?, ?, ?, ?, ?)""",
        (
            "id", "hash", str(audio), str(raw),
            process_voice_memos.transcription_fingerprint(
                settings.whisper_model, settings.language
            ),
            "publish_pending", "2026-01-01T00:00:00Z",
        ),
    )
    db.commit()
    db.close()
    args = process_voice_memos.build_parser(settings).parse_args(
        ["--recordings-dir", str(recordings)]
    )
    assert process_voice_memos.process(args, settings) == 75
    with sqlite3.connect(tmp_path / ".state" / "ingest.sqlite") as db:
        assert db.execute("select status from recordings").fetchone()[0] == "publish_pending"
