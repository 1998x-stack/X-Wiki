"""Independent integration and fault-injection tests for Git release transactions."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import release_gate
from process_voice_memos import git_publish
from release_gate import build_manifest, publish_head


def run(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True, capture_output=True
    ).stdout.strip()


def fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "wiki-repo"
    repo.mkdir()
    run(repo, "init", "-b", "main")
    run(repo, "config", "user.name", "X-Wiki Test")
    run(repo, "config", "user.email", "tests@example.invalid")
    (repo / "wiki" / "concepts").mkdir(parents=True)
    (repo / "wiki" / "concepts" / "idea.md").write_text(
        "# Idea\n\n## 来源\n\n- [[raw/references/note]]\n", encoding="utf-8"
    )
    (repo / "raw" / "references").mkdir(parents=True)
    (repo / "raw" / "references" / "note.md").write_text(
        "# Private source\n", encoding="utf-8"
    )
    (repo / "index.md").write_text("# Index\n", encoding="utf-8")
    (repo / "log.md").write_text("# History\n", encoding="utf-8")
    run(repo, "add", ".")
    run(repo, "commit", "-m", "base")
    return repo


def bare_remote(repo: Path, tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    run(repo, "init", "--bare", str(remote))
    run(repo, "remote", "add", "origin", str(remote))


def journal(repo: Path) -> dict:
    paths = list((repo / ".state" / "releases").glob("*.json"))
    assert len(paths) == 1
    return json.loads(paths[0].read_text(encoding="utf-8"))


def test_manifest_is_deterministic_and_excludes_raw(tmp_path: Path) -> None:
    repo = fixture_repo(tmp_path)
    (repo / ".state").mkdir()
    (repo / ".state" / "secret.txt").write_text("secret", encoding="utf-8")
    first = build_manifest(repo)
    assert first == build_manifest(repo)
    assert first.commit_sha == run(repo, "rev-parse", "HEAD")
    assert len(first.content_sha256) == 64
    paths = {item["path"] for item in first.files}
    assert paths == {"index.md", "log.md", "wiki/concepts/idea.md"}
    assert all("raw/" not in item["path"] for item in first.files)


def test_publish_confirms_remote_and_records_manifest(tmp_path: Path) -> None:
    repo = fixture_repo(tmp_path)
    bare_remote(repo, tmp_path)
    result = git_publish(repo, "origin", "main")
    assert result.commit_sha == run(repo, "rev-parse", "HEAD")
    assert run(repo, "ls-remote", "origin", "refs/heads/main").split()[0] == result.commit_sha
    saved = journal(repo)
    assert saved["status"] == "git_confirmed"
    assert saved["manifest"]["commit_sha"] == result.commit_sha
    assert saved["manifest"]["content_sha256"] == build_manifest(repo).content_sha256


def test_repeated_publication_skips_unnecessary_push(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = fixture_repo(tmp_path)
    bare_remote(repo, tmp_path)
    original = publish_head(repo, "origin", "main")
    previous_run = release_gate.subprocess.run

    def prevent_push(command: list[str], **kwargs: object):
        if command[:2] == ["git", "push"]:
            raise AssertionError("retry should not push an already confirmed commit")
        return previous_run(command, **kwargs)

    monkeypatch.setattr(release_gate.subprocess, "run", prevent_push)
    assert publish_head(repo, "origin", "main") == original
    assert journal(repo)["status"] == "git_confirmed"


def test_crash_after_push_before_confirmation_is_recoverable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = fixture_repo(tmp_path)
    bare_remote(repo, tmp_path)
    original_record = release_gate.record_release
    failures = 0

    def interrupted(*args, **kwargs):
        nonlocal failures
        status = args[-1]
        if status == "git_confirmed" and failures == 0:
            failures += 1
            raise OSError("simulated shutdown after verified remote push")
        return original_record(*args, **kwargs)

    monkeypatch.setattr(release_gate, "record_release", interrupted)
    with pytest.raises(OSError, match="simulated shutdown"):
        publish_head(repo, "origin", "main")
    committed = run(repo, "rev-parse", "HEAD")
    assert run(repo, "ls-remote", "origin", "refs/heads/main").split()[0] == committed
    assert journal(repo)["status"] == "prepared"
    monkeypatch.setattr(release_gate, "record_release", original_record)
    assert publish_head(repo, "origin", "main").commit_sha == committed
    assert journal(repo)["status"] == "git_confirmed"


def test_failed_network_push_remains_prepared_and_retries(tmp_path: Path) -> None:
    repo = fixture_repo(tmp_path)
    run(repo, "remote", "add", "origin", str(tmp_path / "missing.git"))
    with pytest.raises(subprocess.CalledProcessError):
        publish_head(repo, "origin", "main")
    assert journal(repo)["status"] == "prepared"
    remote = tmp_path / "good.git"
    run(repo, "init", "--bare", str(remote))
    run(repo, "remote", "set-url", "origin", str(remote))
    publish_head(repo, "origin", "main")
    assert journal(repo)["status"] == "git_confirmed"


def test_verification_mismatch_does_not_mark_confirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = fixture_repo(tmp_path)
    bare_remote(repo, tmp_path)
    true_run = release_gate.subprocess.run

    def pretend_push(command: list[str], **kwargs: object):
        if command[:2] == ["git", "push"]:
            return subprocess.CompletedProcess(command, 0)
        return true_run(command, **kwargs)

    monkeypatch.setattr(release_gate.subprocess, "run", pretend_push)
    with pytest.raises(RuntimeError, match="Remote ref differs"):
        publish_head(repo, "origin", "main")
    assert journal(repo)["status"] == "prepared"


def test_manifest_changes_only_with_committed_knowledge(tmp_path: Path) -> None:
    repo = fixture_repo(tmp_path)
    before = build_manifest(repo)
    (repo / "wiki" / "concepts" / "idea.md").write_text(
        "# Changed\n\n## 来源\n\n- [[raw/references/note]]\n", encoding="utf-8"
    )
    assert build_manifest(repo) == before
    run(repo, "add", "wiki")
    run(repo, "commit", "-m", "change knowledge")
    assert build_manifest(repo).content_sha256 != before.content_sha256


def test_release_journal_is_not_part_of_public_commit(tmp_path: Path) -> None:
    repo = fixture_repo(tmp_path)
    bare_remote(repo, tmp_path)
    publish_head(repo, "origin", "main")
    assert not run(repo, "ls-tree", "-r", "--name-only", "HEAD", "--", ".state")
