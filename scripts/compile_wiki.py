#!/usr/bin/env python3
"""Invoke pi with the repository skill to compile raw sources into X-Wiki."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def compile_wiki(repo: Path, sources: list[Path], model: str, provider: str) -> None:
    pi = shutil.which("pi") or "/opt/homebrew/bin/pi"
    skill = repo / "skills" / "x-wiki-compiler"
    source_list = "\n".join(f"- {path.relative_to(repo)}" for path in sources)
    prompt = f"""Use the loaded x-wiki-compiler skill to compile these newly ingested sources:

{source_list}

Read the existing wiki before editing. Update only wiki/, index.md, and log.md.
Do not edit raw/, run git, install software, or access network services.
Perform the edits now, then give a concise summary.
"""
    command = [
        pi,
        "--provider",
        provider,
        "--model",
        model,
        "--skill",
        str(skill),
        "--no-session",
        "--approve",
        "--tools",
        "read,write,edit,grep,find,ls",
        "--print",
        prompt,
    ]
    subprocess.run(command, cwd=repo, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--provider", default="iagent")
    parser.add_argument("--model", default="iagent/standard")
    args = parser.parse_args()
    repo = args.repo.resolve()
    sources = [(path if path.is_absolute() else repo / path).resolve() for path in args.sources]
    for source in sources:
        source.relative_to(repo / "raw")
        if not source.is_file():
            parser.error(f"source does not exist: {source}")
    compile_wiki(repo, sources, args.model, args.provider)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
