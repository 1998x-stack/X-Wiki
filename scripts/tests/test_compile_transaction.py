"""Power-interruption simulation for durable Wiki writeback and recovery."""

from __future__ import annotations

from pathlib import Path

import pytest
from compile_transaction import (
    apply_transaction,
    recover_transactions,
    transactions_root,
)
from staged_workspace import atomic_replace_file, repository_digest


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "wiki" / "concepts").mkdir(parents=True)
    (repo / "index.md").write_text("# Original\n", encoding="utf-8")
    (repo / "wiki" / "concepts" / "topic.md").write_text(
        "# Original topic\n", encoding="utf-8"
    )
    return repo


def changed() -> dict[str, bytes | None]:
    return {
        "index.md": b"# Updated\n",
        "wiki/concepts/topic.md": b"# Updated topic\n",
        "wiki/concepts/new.md": b"# New\n",
    }


def test_successful_durable_apply_cleans_journal(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    snapshot = repository_digest(repo)
    assert apply_transaction(
        repo, changed(), write=atomic_replace_file, expected_snapshot=snapshot
    ) == sorted(changed())
    assert (repo / "index.md").read_bytes() == b"# Updated\n"
    assert not list(transactions_root(repo).iterdir())
    assert recover_transactions(repo) == []


def test_simulated_process_interruption_recovers_without_manual_data_loss(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    count = 0

    def interrupted(path: Path, content: bytes) -> None:
        nonlocal count
        count += 1
        atomic_replace_file(path, content)
        if count == 1:
            raise KeyboardInterrupt("simulated power loss")

    with pytest.raises(KeyboardInterrupt, match="power loss"):
        apply_transaction(
            repo,
            changed(),
            write=interrupted,
            expected_snapshot=repository_digest(repo),
        )
    assert list(transactions_root(repo).iterdir())
    restored = recover_transactions(repo)
    assert "index.md" in restored
    assert (repo / "index.md").read_bytes() == b"# Original\n"
    assert (repo / "wiki" / "concepts" / "topic.md").read_bytes() == b"# Original topic\n"
    assert not (repo / "wiki" / "concepts" / "new.md").exists()
    assert not list(transactions_root(repo).iterdir())
    assert recover_transactions(repo) == []


def test_manual_edit_conflict_preserves_user_edits(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    count = 0

    def interrupted(path: Path, content: bytes) -> None:
        nonlocal count
        count += 1
        atomic_replace_file(path, content)
        if count == 1:
            raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        apply_transaction(repo, changed(), write=interrupted)
    (repo / "index.md").write_text("# Manual override\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Manual edit conflicts"):
        recover_transactions(repo)
    assert (repo / "index.md").read_text() == "# Manual override\n"
    assert list(transactions_root(repo).iterdir())


def test_preexisting_snapshot_mismatch_blocks_transaction(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    snapshot = repository_digest(repo)
    (repo / "index.md").write_text("# User changed\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Live repository changed"):
        apply_transaction(
            repo, changed(), write=atomic_replace_file, expected_snapshot=snapshot
        )
    assert (repo / "index.md").read_text() == "# User changed\n"


@pytest.mark.parametrize("bad", ["../README.md", "wiki/../index.md", "raw/voice/x.md"])
def test_unsafe_destination_is_rejected(tmp_path: Path, bad: str) -> None:
    repo = make_repo(tmp_path)
    with pytest.raises(RuntimeError, match="Unsafe compilation journal path"):
        apply_transaction(repo, {bad: b"bad"}, write=atomic_replace_file)


def test_symlinked_destination_is_rejected(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "wiki" / "concepts" / "linked.md").symlink_to(repo / "index.md")
    with pytest.raises(RuntimeError, match="Symlinked compilation"):
        apply_transaction(
            repo, {"wiki/concepts/linked.md": b"bad"}, write=atomic_replace_file
        )
    assert (repo / "index.md").read_bytes() == b"# Original\n"


def test_symlinked_source_is_not_hashed_by_snapshot(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "wiki" / "concepts" / "linked.md").symlink_to(repo / "index.md")
    with pytest.raises(RuntimeError, match="Unsafe symlink"):
        repository_digest(repo)
