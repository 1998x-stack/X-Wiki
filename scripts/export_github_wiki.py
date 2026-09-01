#!/usr/bin/env python3
"""Export local wiki Markdown into GitHub Wiki's flat page namespace."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


WIKI_LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def page_name(path: str) -> str:
    return path.removeprefix("wiki/").replace("/", "--")


def rewrite(text: str, source_key: str, pages: dict[str, str]) -> str:
    def replacement(match: re.Match[str]) -> str:
        target = match.group(1)
        label = match.group(2) or Path(target).name.replace("-", " ").title()
        if target.startswith("wiki/"):
            return f"[[{label}|{page_name(target)}]]"
        if target.startswith("raw/"):
            return f"{label}（本地证据）"
        destination = pages.get(target) or pages.get(Path(source_key).parent.joinpath(target).as_posix())
        if destination:
            return f"[[{label}|{destination}]]"
        return f"{label}（本地证据）"

    return WIKI_LINK.sub(replacement, text)


def export(repo: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for stale in output.glob("*.md"):
        stale.unlink()
    sources = sorted((repo / "wiki").rglob("*.md"))
    pages: dict[str, str] = {}
    for source in sources:
        relative = source.relative_to(repo).with_suffix("").as_posix()
        destination = page_name(relative)
        pages[relative] = destination
        pages.setdefault(Path(relative).name, destination)

    home = rewrite((repo / "index.md").read_text(encoding="utf-8"), "index", pages)
    (output / "Home.md").write_text(home, encoding="utf-8")
    sidebar = ["- [[Home]]"]
    for source in sources:
        relative = source.relative_to(repo).with_suffix("").as_posix()
        name = page_name(relative)
        content = rewrite(source.read_text(encoding="utf-8"), relative, pages)
        (output / f"{name}.md").write_text(content, encoding="utf-8")
        title = content.splitlines()[0].removeprefix("# ").strip() or name
        sidebar.append(f"- [[{title}|{name}]]")
    (output / "_Sidebar.md").write_text("\n".join(sidebar) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    export(args.repo.resolve(), args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
