"""Dynamic MkDocs navigation cannot silently omit newly compiled Wiki pages."""

from __future__ import annotations

from pathlib import Path

import pytest
from mkdocs_nav import build_navigation, on_config


def site(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    (docs / "wiki" / "concepts").mkdir(parents=True)
    (docs / "wiki" / "entities").mkdir(parents=True)
    (docs / "index.md").write_text("# Home\n", encoding="utf-8")
    (docs / "wiki" / "concepts" / "a.md").write_text(
        "# Alpha\n", encoding="utf-8"
    )
    (docs / "wiki" / "entities" / "person.md").write_text(
        "# A Person\n", encoding="utf-8"
    )
    return docs


def test_every_page_is_in_dynamic_navigation(tmp_path: Path) -> None:
    docs = site(tmp_path)
    expected = [
        {"首页": "index.md"},
        {"概念": [{"Alpha": "wiki/concepts/a.md"}]},
        {"人物": [{"A Person": "wiki/entities/person.md"}]},
    ]
    assert build_navigation(docs) == expected
    assert on_config({"docs_dir": str(docs), "nav": []})["nav"] == expected


def test_new_compiled_page_appears_without_yaml_edit(tmp_path: Path) -> None:
    docs = site(tmp_path)
    new = docs / "wiki" / "concepts" / "new-idea.md"
    new.write_text("# 新概念\n", encoding="utf-8")
    assert {"新概念": "wiki/concepts/new-idea.md"} in build_navigation(docs)[1]["概念"]


def test_unknown_category_is_never_silently_omitted(tmp_path: Path) -> None:
    docs = site(tmp_path)
    unexpected = docs / "wiki" / "unlisted"
    unexpected.mkdir()
    (unexpected / "orphan.md").write_text("# Orphan\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Unlisted knowledge pages"):
        build_navigation(docs)


def test_symlink_in_navigation_is_rejected(tmp_path: Path) -> None:
    docs = site(tmp_path)
    (docs / "wiki" / "concepts" / "link.md").symlink_to(
        docs / "wiki" / "concepts" / "a.md"
    )
    with pytest.raises(RuntimeError, match="Symlinked navigation"):
        build_navigation(docs)
