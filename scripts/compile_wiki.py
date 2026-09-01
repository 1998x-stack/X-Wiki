#!/usr/bin/env python3
"""Invoke pi with the repository skill to compile raw sources into X-Wiki."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
from pathlib import Path

from xwiki_config import Settings

ALLOWED_OUTPUTS = {"index.md", "log.md"}


def tree_digest(root: Path) -> dict[Path, str]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


IGNORED_SNAPSHOT_PARTS = {
    ".git",
    ".site-docs",
    ".state",
    ".venv",
    "site",
    ".codegraph",
    ".pytest_cache",
    ".ruff_cache",
    ".omo",
    ".workbuddy-ai",
    "__pycache__",
    ".env",
    ".DS_Store",
}


def repository_digest(repo: Path) -> dict[str, str]:
    digest: dict[str, str] = {}
    for root, directories, files in os.walk(repo):
        directories[:] = [name for name in directories if name not in IGNORED_SNAPSHOT_PARTS]
        root_path = Path(root)
        for name in files:
            if name in IGNORED_SNAPSHOT_PARTS:
                continue
            path = root_path / name
            relative = path.relative_to(repo).as_posix()
            digest[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def validate_model_changes(before: dict[str, str], after: dict[str, str]) -> None:
    changed_by_model = {
        path for path in before.keys() | after.keys() if before.get(path) != after.get(path)
    }
    invalid = sorted(
        path
        for path in changed_by_model
        if path not in ALLOWED_OUTPUTS and not path.startswith("wiki/")
    )
    if invalid:
        raise RuntimeError(
            f"wiki compiler changed files outside its boundary: {', '.join(invalid)}"
        )


def compile_wiki(
    repo: Path,
    sources: list[Path],
    model: str,
    provider: str,
    *,
    pi_bin: str,
    timeout_seconds: int,
) -> None:
    skill = repo / "skills" / "x-wiki-compiler"
    if not skill.is_dir():
        raise FileNotFoundError(f"X-Wiki skill not found: {skill}")
    pi_path = Path(pi_bin).expanduser()
    if pi_path.parent != Path(".") and not pi_path.exists():
        raise FileNotFoundError(f"pi executable not found: {pi_bin}")

    source_list = "\n".join(f"- {path.relative_to(repo)}" for path in sources)
    prompt = f"""Use the loaded x-wiki-compiler skill to compile these newly ingested sources:

{source_list}

Read the existing wiki before editing. Update only wiki/, index.md, and log.md.
Do not edit raw/, run git, install software, or access network services.
Perform the edits now, validate every new link, then give a concise summary.
"""
    raw_before = tree_digest(repo / "raw")
    repository_before = repository_digest(repo)
    command = [
        pi_bin,
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
    subprocess.run(command, cwd=repo, check=True, timeout=timeout_seconds)
    if tree_digest(repo / "raw") != raw_before:
        raise RuntimeError("wiki compiler modified immutable raw evidence")
    validate_model_changes(repository_before, repository_digest(repo))


def main() -> int:
    repo_default = Path(__file__).resolve().parents[1]
    settings = Settings.load(repo_default)
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--repo", type=Path, default=repo_default)
    parser.add_argument("--provider", default=settings.llm_provider)
    parser.add_argument("--model", default=settings.llm_model)
    parser.add_argument("--pi-bin", default=settings.pi_bin)
    parser.add_argument("--timeout", type=int, default=settings.compile_timeout_seconds)
    args = parser.parse_args()
    repo = args.repo.expanduser().resolve()
    sources = [(path if path.is_absolute() else repo / path).resolve() for path in args.sources]
    for source in sources:
        try:
            source.relative_to(repo / "raw")
        except ValueError:
            parser.error(f"source is outside raw/: {source}")
        if not source.is_file():
            parser.error(f"source does not exist: {source}")
    compile_wiki(
        repo,
        sources,
        args.model,
        args.provider,
        pi_bin=args.pi_bin,
        timeout_seconds=args.timeout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
