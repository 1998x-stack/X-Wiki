"""ARCH-00C: verify candidate -> private approval -> separate public promotion.

These are file-level human preview gates, NOT semantic source-grounding nor
production user authentication.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import compile_wiki
import pytest
from private_review import approve_private, promote_public, review_preview


def make_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    (repo / "raw" / "references").mkdir(parents=True)
    (repo / "raw" / "references" / "note.md").write_text(
        "# A synthetic source\n", encoding="utf-8"
    )
    (repo / "raw" / "voice").mkdir()
    source = repo / "raw" / "voice" / "memo.md"
    source.write_text("# Initial thought\n", encoding="utf-8")
    (repo / "wiki" / "concepts").mkdir(parents=True)
    (repo / "wiki" / "concepts" / "topic.md").write_text(
        "# Topic\n\n## 来源\n\n- [[raw/references/note]]\n",
        encoding="utf-8",
    )
    (repo / "index.md").write_text("# Home\n", encoding="utf-8")
    (repo / "log.md").write_text("# History\n", encoding="utf-8")
    (repo / "scripts" / "skills" / "x-wiki-compiler").mkdir(parents=True)
    (repo / "scripts" / "skills" / "x-wiki-compiler" / "SKILL.md").write_text(
        "Fake compiler instructions", encoding="utf-8"
    )
    return repo, source


def fake_compile(
    repo: Path,
    source: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    content: str = "# New knowledge\n\n## 来源\n\n- [[raw/references/note]]\n",
) -> str:
    def run(command: list[str], *, cwd: Path, **kwargs: object) -> subprocess.CompletedProcess:
        assert cwd != repo
        assert (cwd / "raw" / "voice" / "memo.md").read_bytes() == source.read_bytes()
        assert (repo / "wiki" / "concepts" / "topic.md").read_text().startswith("# Topic")
        (cwd / "wiki" / "concepts" / "topic.md").write_text(content, encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(compile_wiki.subprocess, "run", run)
    candidate = compile_wiki.compile_wiki(
        repo, [source], "model", "provider", pi_bin="pi",
        timeout_seconds=20, mode="review_first", external_processing_approved=True,
    )
    assert candidate is not None
    return candidate


def test_review_first_no_live_changes_and_no_git(tmp_path: Path, monkeypatch) -> None:
    repo, source = make_repo(tmp_path)
    before = (repo / "wiki" / "concepts" / "topic.md").read_bytes()
    candidate = fake_compile(repo, source, monkeypatch)
    assert len(candidate) == 64
    assert (repo / "wiki" / "concepts" / "topic.md").read_bytes() == before
    assert not (repo / ".git").exists()
    manifest = json.loads(
        (repo / ".state" / "review-candidates" / candidate / "candidate.json").read_text()
    )
    assert manifest["changes"][0]["path"] == "wiki/concepts/topic.md"
    assert manifest["sources"] == ["raw/voice/memo.md"]


def test_explicit_private_approval_does_not_touch_public_knowledge(
    tmp_path: Path, monkeypatch
) -> None:
    repo, source = make_repo(tmp_path)
    candidate = fake_compile(repo, source, monkeypatch)
    before = (repo / "wiki" / "concepts" / "topic.md").read_bytes()
    with pytest.raises(PermissionError, match="full candidate"):
        approve_private(repo, candidate, confirmation="wrong")
    diff, public_token = review_preview(repo, candidate)
    assert "# Topic" in diff and "# New knowledge" in diff
    assert public_token != candidate
    assert not (repo / ".state" / "approved-knowledge").exists()
    approved = approve_private(repo, candidate, confirmation=candidate)
    assert approved == approve_private(repo, candidate, confirmation=candidate)
    assert (repo / "wiki" / "concepts" / "topic.md").read_bytes() == before
    with pytest.raises(PermissionError, match="separate preview"):
        promote_public(repo, candidate, confirmation=candidate)
    assert (repo / "wiki" / "concepts" / "topic.md").read_bytes() == before


def test_public_promotion_requires_second_token_and_never_pushes(
    tmp_path: Path, monkeypatch
) -> None:
    repo, source = make_repo(tmp_path)
    candidate = fake_compile(repo, source, monkeypatch)
    approve_private(repo, candidate, confirmation=candidate)
    _, token = review_preview(repo, candidate)
    result = promote_public(repo, candidate, confirmation=token)
    assert result == ["wiki/concepts/topic.md"]
    assert (repo / "wiki" / "concepts" / "topic.md").read_text().startswith("# New knowledge")
    assert not (repo / ".git").exists()
    marker = json.loads(
        (repo / ".state" / "public-promotions" / (candidate + ".json")).read_text()
    )
    assert marker["public_fingerprint"] == token


def test_modified_live_knowledge_refuses_private_approval(
    tmp_path: Path, monkeypatch
) -> None:
    repo, source = make_repo(tmp_path)
    candidate = fake_compile(repo, source, monkeypatch)
    (repo / "wiki" / "concepts" / "topic.md").write_text("# Human edit\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="knowledge changed"):
        approve_private(repo, candidate, confirmation=candidate)
    assert (repo / "wiki" / "concepts" / "topic.md").read_text() == "# Human edit\n"


def test_modified_live_knowledge_refuses_public_promotion(
    tmp_path: Path, monkeypatch
) -> None:
    repo, source = make_repo(tmp_path)
    candidate = fake_compile(repo, source, monkeypatch)
    approve_private(repo, candidate, confirmation=candidate)
    _, token = review_preview(repo, candidate)
    (repo / "wiki" / "concepts" / "topic.md").write_text("# Newer edit\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="knowledge changed"):
        promote_public(repo, candidate, confirmation=token)
    assert (repo / "wiki" / "concepts" / "topic.md").read_text() == "# Newer edit\n"


def test_invalid_wiki_candidate_never_reaches_public_tree(
    tmp_path: Path, monkeypatch
) -> None:
    repo, source = make_repo(tmp_path)
    candidate = fake_compile(repo, source, monkeypatch, content="# No source\n")
    approve_private(repo, candidate, confirmation=candidate)
    _, token = review_preview(repo, candidate)
    with pytest.raises(RuntimeError, match="lint"):
        promote_public(repo, candidate, confirmation=token)
    assert (repo / "wiki" / "concepts" / "topic.md").read_text().startswith("# Topic")


def test_candidate_blob_corruption_blocks_review_and_promotion(tmp_path: Path, monkeypatch) -> None:
    repo, source = make_repo(tmp_path)
    candidate = fake_compile(repo, source, monkeypatch)
    directory = repo / ".state" / "review-candidates" / candidate
    payload = next((directory / "blobs").iterdir())
    payload.write_text("corrupted", encoding="utf-8")
    with pytest.raises(RuntimeError, match="damaged"):
        approve_private(repo, candidate, confirmation=candidate)
    with pytest.raises(RuntimeError, match="damaged"):
        review_preview(repo, candidate)


def test_symlinked_candidate_blob_is_rejected(tmp_path: Path, monkeypatch) -> None:
    repo, source = make_repo(tmp_path)
    candidate = fake_compile(repo, source, monkeypatch)
    directory = repo / ".state" / "review-candidates" / candidate
    payload = next((directory / "blobs").iterdir())
    payload.unlink()
    payload.symlink_to(repo / "index.md")
    with pytest.raises(RuntimeError, match="blob missing or damaged"):
        approve_private(repo, candidate, confirmation=candidate)


def test_review_first_requires_explicit_model_consent_before_pi(
    tmp_path: Path, monkeypatch
) -> None:
    repo, source = make_repo(tmp_path)
    def blocked(*args, **kwargs):
        raise AssertionError("model must never start without external processing consent")
    monkeypatch.setattr(compile_wiki.subprocess, "run", blocked)
    with pytest.raises(PermissionError, match="explicit permission"):
        compile_wiki.compile_wiki(
            repo, [source], "model", "provider", pi_bin="pi",
            timeout_seconds=20, mode="review_first",
        )
    assert not (repo / ".state" / "review-candidates").exists()


def test_source_outside_raw_rejected_even_in_review_first(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path)
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    with pytest.raises(ValueError, match="outside raw"):
        compile_wiki.compile_wiki(
            repo, [outside], "model", "provider", pi_bin="pi",
            timeout_seconds=20, mode="review_first", external_processing_approved=True,
        )


def test_preview_fingerprint_is_bound_to_candidate_not_a_secret(tmp_path: Path, monkeypatch):
    repo, source = make_repo(tmp_path)
    candidate = fake_compile(repo, source, monkeypatch)
    _, public_token = review_preview(repo, candidate)
    expected = hashlib.sha256(
        json.dumps(
            {"action": "public-promotion", "candidate": candidate},
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert public_token == expected
