"""Independent deterministic Wiki publication checks."""

from __future__ import annotations

from pathlib import Path

import pytest
from prepare_site import prepare, reset_output
from wiki_links import convert_links, iter_wikilinks
from wiki_lint import lint_wiki


def wiki_fixture(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "wiki" / "concepts").mkdir(parents=True)
    (repo / "raw" / "references").mkdir(parents=True)
    (repo / "raw" / "references" / "paper.md").write_text("# paper\n", encoding="utf-8")
    (repo / "wiki" / "concepts" / "idea.md").write_text(
        "# Idea\n\n## 来源\n\n- [[raw/references/paper]]\n", encoding="utf-8"
    )
    (repo / "index.md").write_text(
        "# Index\n\n[[wiki/concepts/idea|Idea]]\n", encoding="utf-8"
    )
    return repo


def errors(repo: Path) -> set[str]:
    return {finding.code for finding in lint_wiki(repo) if finding.severity == "error"}


def test_current_schema_passes_without_frontmatter(tmp_path: Path) -> None:
    repo = wiki_fixture(tmp_path)
    assert not errors(repo)
    prepare(repo, tmp_path / "site-output", strict=True)


def test_missing_page_fails_lint_and_strict_render(tmp_path: Path) -> None:
    repo = wiki_fixture(tmp_path)
    (repo / "index.md").write_text("[[wiki/concepts/lost]]\n", encoding="utf-8")
    assert "BROKEN_LINK" in errors(repo)
    with pytest.raises(ValueError, match="Wiki lint"):
        prepare(repo, tmp_path / "public", strict=True)
    assert not (tmp_path / "public").exists()


def test_missing_tracked_reference_is_error(tmp_path: Path) -> None:
    repo = wiki_fixture(tmp_path)
    (repo / "raw" / "references" / "paper.md").unlink()
    assert "BROKEN_REFERENCE" in errors(repo)


def test_untracked_voice_evidence_is_allowed_and_private(tmp_path: Path) -> None:
    repo = wiki_fixture(tmp_path)
    (repo / "wiki" / "concepts" / "idea.md").write_text(
        "# Idea\n\n## 来源\n\n- [[raw/voice/2026/11/secret-file|证据]]\n",
        encoding="utf-8",
    )
    assert not errors(repo)
    output = tmp_path / "published"
    prepare(repo, output, strict=True)
    text = (output / "wiki" / "concepts" / "idea.md").read_text()
    assert 'class="local-evidence"' in text
    assert "raw/voice/" not in text
    assert "secret-file" not in text


def test_traversal_and_unsafe_links_fail(tmp_path: Path) -> None:
    repo = wiki_fixture(tmp_path)
    (repo / "index.md").write_text(
        "[[../.env]] [[/etc/passwd]] [[raw/voice/../secret]]\n", encoding="utf-8"
    )
    assert "UNSAFE_LINK" in errors(repo)


def test_rejects_duplicate_ids_and_mismatched_types(tmp_path: Path) -> None:
    repo = wiki_fixture(tmp_path)
    (repo / "wiki" / "concepts" / "idea.md").write_text(
        "---\ntype: entity\ntitle: Idea\nid: duplicate\n---\n"
        "# Idea\n\n## 来源\n\n- [[raw/references/paper]]\n",
        encoding="utf-8",
    )
    (repo / "wiki" / "concepts" / "other.md").write_text(
        "---\ntype: concept\ntitle: Other\nid: duplicate\n---\n"
        "# Other\n\n## 来源\n\n- [[raw/references/paper]]\n",
        encoding="utf-8",
    )
    assert {"BAD_PAGE_TYPE", "DUPLICATE_ID"} <= errors(repo)


def test_requires_provenance_and_last_source_section(tmp_path: Path) -> None:
    repo = wiki_fixture(tmp_path)
    (repo / "wiki" / "concepts" / "idea.md").write_text(
        "# Idea\n\n## 来源\n\n## Later\n", encoding="utf-8"
    )
    assert {"MISSING_PROVENANCE", "SOURCES_NOT_LAST"} <= errors(repo)


@pytest.mark.parametrize(
    "secret",
    [
        "-----BEGIN PRIVATE KEY-----",
        "ghp_" + "a" * 35,
        "/Users/example/Library/recordings",
        "person@example.com",
        "13800138000",
    ],
)
def test_public_private_content_is_flagged(tmp_path: Path, secret: str) -> None:
    repo = wiki_fixture(tmp_path)
    (repo / "index.md").write_text("# Index\n" + secret, encoding="utf-8")
    assert any(code.startswith("PRIVATE_") for code in errors(repo))
    with pytest.raises(ValueError, match="Wiki lint"):
        prepare(repo, tmp_path / "published", strict=True)


def test_code_fences_and_inline_code_are_not_rewritten(tmp_path: Path) -> None:
    root = tmp_path
    (root / "wiki").mkdir()
    current = root / "wiki" / "page.md"
    (root / "wiki" / "target.md").write_text("# Target", encoding="utf-8")
    text = (
        "```markdown\n[[wiki/missing]]\n```\n"
        "`[[wiki/missing]]` [[target|Valid]]\n"
    )
    assert [x.target for x in iter_wikilinks(text)] == ["target"]
    rendered = convert_links(text, current, root, strict=True)
    assert "`[[wiki/missing]]`" in rendered
    assert "[Valid](target.md)" in rendered


def test_html_alias_is_escaped_in_rendered_wiki(tmp_path: Path) -> None:
    root = tmp_path
    (root / "wiki").mkdir()
    current = root / "wiki" / "page.md"
    (root / "wiki" / "target.md").write_text("content", encoding="utf-8")
    rendered = convert_links(
        "[[target|<img src=x onerror=alert(1)>]] "
        "[[raw/voice/private|<svg/onload=alert(1)>]]",
        current, root, strict=True,
    )
    assert "<img" not in rendered and "<svg" not in rendered
    assert "&lt;img" in rendered and "&lt;svg" in rendered


def test_guard_refuses_unmarked_existing_output(tmp_path: Path) -> None:
    repo = wiki_fixture(tmp_path)
    output = tmp_path / "important-data"
    output.mkdir()
    (output / "valuable.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="non-generated"):
        reset_output(output, repo)
    assert (output / "valuable.txt").read_text() == "keep"


def test_guard_refuses_repo_children_and_ancestors(tmp_path: Path) -> None:
    repo = wiki_fixture(tmp_path)
    with pytest.raises(ValueError, match="protected"):
        reset_output(tmp_path, repo)
    with pytest.raises(ValueError, match="protected"):
        reset_output(repo / "wiki", repo)


def test_guard_allows_rebuild_of_marked_output(tmp_path: Path) -> None:
    repo = wiki_fixture(tmp_path)
    output = tmp_path / "public"
    prepare(repo, output, strict=True)
    (output / "stale.txt").write_text("old", encoding="utf-8")
    prepare(repo, output, strict=True)
    assert not (output / "stale.txt").exists()
