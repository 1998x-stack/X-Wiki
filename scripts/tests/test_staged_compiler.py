"""Staged compiler tests: success, timeouts, unexpected writes, rollback."""

from __future__ import annotations

import subprocess
from pathlib import Path

import compile_wiki
import pytest
import staged_workspace


def make_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    (repo / "scripts" / "skills" / "x-wiki-compiler").mkdir(parents=True)
    (repo / "scripts" / "skills" / "x-wiki-compiler" / "SKILL.md").write_text(
        "Use only the wiki files.\n", encoding="utf-8"
    )
    (repo / "wiki").mkdir()
    (repo / "wiki" / "topic.md").write_text("# Original\n", encoding="utf-8")
    (repo / "index.md").write_text("# Index\n", encoding="utf-8")
    (repo / "log.md").write_text("# Log\n", encoding="utf-8")
    (repo / "raw" / "voice").mkdir(parents=True)
    source = repo / "raw" / "voice" / "memo.md"
    source.write_text("# Immutable evidence\n", encoding="utf-8")
    return repo, source


def compile_source(repo: Path, source: Path) -> None:
    compile_wiki.compile_wiki(
        repo, [source], "model", "provider", pi_bin="pi", timeout_seconds=20
    )


def test_staging_success_applies_validated_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, source = make_repo(tmp_path)

    def fake_pi(command: list[str], *, cwd: Path, **kwargs: object) -> object:
        assert cwd != repo
        assert (cwd / "raw" / "voice" / "memo.md").read_text() == source.read_text()
        assert (cwd / "wiki" / "topic.md").read_text() == "# Original\n"
        assert (repo / "wiki" / "topic.md").read_text() == "# Original\n"
        assert str(cwd / "scripts" / "skills" / "x-wiki-compiler") in command
        (cwd / "wiki" / "topic.md").write_text("# Updated\n", encoding="utf-8")
        (cwd / "wiki" / "new.md").write_text("# New\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(compile_wiki.subprocess, "run", fake_pi)
    compile_source(repo, source)
    assert (repo / "wiki" / "topic.md").read_text() == "# Updated\n"
    assert (repo / "wiki" / "new.md").read_text() == "# New\n"
    assert source.read_text() == "# Immutable evidence\n"


def test_timeout_discards_partial_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, source = make_repo(tmp_path)

    def timeout_pi(command: list[str], *, cwd: Path, **kwargs: object) -> object:
        (cwd / "wiki" / "topic.md").write_text("incomplete", encoding="utf-8")
        raise subprocess.TimeoutExpired(command, timeout=20)

    monkeypatch.setattr(compile_wiki.subprocess, "run", timeout_pi)
    with pytest.raises(subprocess.TimeoutExpired):
        compile_source(repo, source)
    assert (repo / "wiki" / "topic.md").read_text() == "# Original\n"


def test_unauthorized_candidate_edit_is_discarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, source = make_repo(tmp_path)

    def bad_pi(command: list[str], *, cwd: Path, **kwargs: object) -> object:
        (cwd / "wiki" / "topic.md").write_text("changed", encoding="utf-8")
        (cwd / "README.md").write_text("illegal", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(compile_wiki.subprocess, "run", bad_pi)
    with pytest.raises(RuntimeError, match="outside its boundary"):
        compile_source(repo, source)
    assert (repo / "wiki" / "topic.md").read_text() == "# Original\n"


def test_symlink_in_candidate_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, source = make_repo(tmp_path)

    def bad_pi(command: list[str], *, cwd: Path, **kwargs: object) -> object:
        (cwd / "wiki" / "external.md").symlink_to("/etc/passwd")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(compile_wiki.subprocess, "run", bad_pi)
    with pytest.raises(RuntimeError, match="symlink is not allowed"):
        compile_source(repo, source)
    assert not (repo / "wiki" / "external.md").exists()


def test_concurrent_live_edit_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, source = make_repo(tmp_path)

    def racing_pi(command: list[str], *, cwd: Path, **kwargs: object) -> object:
        (cwd / "wiki" / "topic.md").write_text("agent output", encoding="utf-8")
        (repo / "wiki" / "topic.md").write_text("human edit", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(compile_wiki.subprocess, "run", racing_pi)
    with pytest.raises(RuntimeError, match="Live repository changed"):
        compile_source(repo, source)
    assert (repo / "wiki" / "topic.md").read_text() == "human edit"


def test_apply_failure_restores_original_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, source = make_repo(tmp_path)

    def fake_pi(command: list[str], *, cwd: Path, **kwargs: object) -> object:
        (cwd / "index.md").write_text("new index", encoding="utf-8")
        (cwd / "wiki" / "topic.md").write_text("new topic", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(compile_wiki.subprocess, "run", fake_pi)
    real_atomic = staged_workspace.atomic_replace_file
    writes = 0

    def failing_atomic(path: Path, payload: bytes) -> None:
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError("simulated disk failure")
        real_atomic(path, payload)

    monkeypatch.setattr(staged_workspace, "atomic_replace_file", failing_atomic)
    with pytest.raises(OSError, match="simulated disk failure"):
        compile_source(repo, source)
    assert (repo / "index.md").read_text() == "# Index\n"
    assert (repo / "wiki" / "topic.md").read_text() == "# Original\n"


def test_raw_source_outside_repo_is_rejected(tmp_path: Path) -> None:
    repo, _source = make_repo(tmp_path)
    external = tmp_path / "external.md"
    external.write_text("secret", encoding="utf-8")
    with pytest.raises(ValueError, match="outside raw"):
        compile_source(repo, external)
