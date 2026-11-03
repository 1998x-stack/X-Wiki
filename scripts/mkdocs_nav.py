"""Automatically include every public knowledge page in the MkDocs navigation."""

from __future__ import annotations

import re
from pathlib import Path

HEADLINE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
SECTIONS = (
    ("synthesis", "综合"),
    ("concepts", "概念"),
    ("entities", "人物"),
    ("decisions", "决策"),
    ("projects", "项目"),
)


def title_for(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = HEADLINE.search(text)
    return match.group(1).strip() if match else path.stem.replace("-", " ").title()


def build_navigation(docs_dir: Path) -> list[dict[str, object]]:
    """Enumerate the prepared *public* documents, not the private raw tree."""
    docs_dir = docs_dir.resolve()
    index = docs_dir / "index.md"
    if not index.is_file():
        raise FileNotFoundError("Generated MkDocs index.md is missing")
    nav: list[dict[str, object]] = [{"首页": "index.md"}]
    wiki = docs_dir / "wiki"
    for folder_name, section_title in SECTIONS:
        folder = wiki / folder_name
        if not folder.is_dir():
            continue
        pages: list[dict[str, str]] = []
        for path in sorted(folder.glob("*.md"), key=lambda p: p.name):
            if path.is_symlink():
                raise RuntimeError(f"Symlinked navigation page: {path}")
            pages.append({title_for(path): path.relative_to(docs_dir).as_posix()})
        if pages:
            nav.append({section_title: pages})
    # New categories cannot silently disappear from the site navigation.
    found = {
        destination
        for section in nav
        for value in section.values()
        for destination in (
            [value] if isinstance(value, str)
            else [path for item in value for path in item.values()]
        )
    }
    unlisted = {
        page.relative_to(docs_dir).as_posix() for page in wiki.rglob("*.md")
    } - found
    if unlisted:
        raise RuntimeError(f"Unlisted knowledge pages: {', '.join(sorted(unlisted))}")
    return nav


def on_config(config):
    config["nav"] = build_navigation(Path(config["docs_dir"]))
    return config
