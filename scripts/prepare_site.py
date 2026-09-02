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
        target = match.group(1).strip()
        label = (match.group(2) or Path(target).name.replace("-", " ").title()).strip()
        if target.startswith("raw/"):
            return f'<span class="local-evidence" title="原始证据仅保留在本机">{label}</span>'
        if target.startswith("wiki/"):
            target_path = site_root / f"{target}.md"
        else:
            target_path = current.parent / f"{target}.md"
        if not target_path.is_file():
            return f'<span class="unresolved-link" title="页面尚未建立">{label}</span>'
        relative = Path(os.path.relpath(target_path, current.parent)).as_posix()
        return f"[{label}]({relative})"

    return WIKI_LINK.sub(replacement, text)


def reset_output(output: Path, repo: Path) -> None:
    protected = {Path("/"), Path.home().resolve(), repo.resolve()}
    if output.resolve() in protected:
        raise ValueError(f"refusing to replace protected directory: {output}")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)


def prepare(repo: Path, output: Path) -> None:
    reset_output(output, repo)
    shutil.copy2(repo / "index.md", output / "index.md")
    shutil.copytree(repo / "wiki", output / "wiki")
    assets = repo / "sites" / "assets"
    if assets.is_dir():
        shutil.copytree(assets, output / "sites" / "assets")
    not_found = repo / "sites" / "content" / "404.md"
    if not_found.is_file():
        shutil.copy2(not_found, output / "404.md")
    for path in output.rglob("*.md"):
        path.write_text(
            convert_links(path.read_text(encoding="utf-8"), path, output),
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = args.repo.expanduser().resolve()
    prepare(repo, (args.output or repo / "sites" / ".site-docs").expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
