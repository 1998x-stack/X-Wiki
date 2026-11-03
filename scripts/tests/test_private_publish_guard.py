"""Public site preparation and Git boundary fail-closed regressions."""

from __future__ import annotations

from pathlib import Path

import pytest
from prepare_site import prepare
from release_gate import publish_head


@pytest.mark.parametrize(
    "frontmatter",
    [
        "---\nvisibility: private\n---\n",
        "---\nprivacy_scope: private\n---\n",
        "---\npublished: false\n---\n",
    ],
)
def test_private_marked_wiki_is_not_exported(
    tmp_path: Path, frontmatter: str
) -> None:
    repo = tmp_path / "repository"
    (repo / "wiki").mkdir(parents=True)
    (repo / "index.md").write_text("# Home\n", encoding="utf-8")
    (repo / "wiki" / "secret.md").write_text(
        frontmatter + "# Private notes\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="private-marked"):
        prepare(repo, tmp_path / "output")
    assert not (tmp_path / "output" / "wiki" / "secret.md").exists()


def test_review_first_git_publish_is_denied_without_touching_repo(tmp_path: Path) -> None:
    with pytest.raises(PermissionError, match="review-first"):
        publish_head(tmp_path, "origin", "main", pipeline_mode="review_first")
    assert not (tmp_path / ".state" / "releases").exists()
