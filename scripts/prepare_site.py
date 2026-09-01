#!/usr/bin/env python3
"""Prepare publishable MkDocs content from the local wiki layer."""

from __future__ import annotations

import argparse
import os
import re
import shutil
from pathlib import Path


WIKI_LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def convert_links(text: str, current: Path, site_root: Path) -> str:
    def replacement(match: re.Match[str]) -> str:
        target = match.group(1)
        label = match.group(2) or Path(target).name.replace("-", " ").title()
        if target.startswith("raw/"):
            return f"{label}（本地证据）"
        if target.startswith("wiki/"):
            target_path = site_root / f"{target}.md"
        else:
            target_path = current.parent / f"{target}.md"
        if not target_path.exists():
            return label
        relative = Path(os.path.relpath(target_path, current.parent)).as_posix()
        return f"[{label}]({relative})"

    return WIKI_LINK.sub(replacement, text)


def prepare(repo: Path, output: Path) -> None:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    shutil.copy2(repo / "index.md", output / "index.md")
    shutil.copytree(repo / "wiki", output / "wiki")
    for path in output.rglob("*.md"):
        path.write_text(convert_links(path.read_text(encoding="utf-8"), path, output), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    prepare(repo, (args.output or repo / ".site-docs").resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
