#!/usr/bin/env python3
"""Compile raw evidence through pi in a disposable staging workspace."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from staged_workspace import (
    apply_staged_changes,
    reject_symlinks,
    repository_digest,
    stage_source_tree,
    validate_model_changes,
)
from xwiki_config import Settings


def compile_wiki(
    repo: Path,
    sources: list[Path],
    model: str,
    provider: str,
    *,
    pi_bin: str,
    timeout_seconds: int,
) -> None:
    """Compile into staging and apply only a fully validated candidate.

    This is a *staged-write/rollback* boundary, not an OS-level sandbox:
    external pi tools may still have access to files outside the workspace.
    """
    repo = repo.expanduser().resolve()
    skill = repo / "scripts" / "skills" / "x-wiki-compiler"
    if not skill.is_dir():
        raise FileNotFoundError(f"X-Wiki skill not found: {skill}")
    pi_path = Path(pi_bin).expanduser()
    if pi_path.parent != Path(".") and not pi_path.exists():
        raise FileNotFoundError(f"pi executable not found: {pi_bin}")

    raw_root = (repo / "raw").resolve()
    relative_sources: list[Path] = []
    for source in sources:
        absolute = (source if source.is_absolute() else repo / source).resolve()
        try:
            absolute.relative_to(raw_root)
        except ValueError as error:
            raise ValueError(f"source is outside raw/: {source}") from error
        if not absolute.is_file():
            raise FileNotFoundError(f"raw source not found: {source}")
        relative_sources.append(absolute.relative_to(repo))

    source_list = "\n".join(f"- {path.as_posix()}" for path in relative_sources)
    prompt = f"""Use the loaded x-wiki-compiler skill to compile these newly ingested sources:

{source_list}

You are in a temporary staging workspace, not the real repository.
Read the existing wiki before editing. Update only wiki/, index.md, and log.md.
Use paths relative to this workspace only. Do not access external filesystem paths.
Do not edit raw/, run git, install software, or access network services.
Perform the edits now, validate every new link, then give a concise summary.
"""

    # Capture ALL live repository files before model execution. A third-party
    # agent that changes the live tree (or a concurrent human edit) aborts apply.
    live_before = repository_digest(repo)
    with tempfile.TemporaryDirectory(prefix="xwiki-compile-") as directory:
        staged = Path(directory) / "workspace"
        staged.mkdir()
        stage_source_tree(repo, staged)
        before = repository_digest(staged)
        staged_skill = staged / "scripts" / "skills" / "x-wiki-compiler"

        command = [
            pi_bin,
            "--provider",
            provider,
            "--model",
            model,
            "--skill",
            str(staged_skill),
            "--no-session",
            "--approve",
            "--tools",
            "read,write,edit,grep,find,ls",
            "--print",
            prompt,
        ]
        try:
            subprocess.run(command, cwd=staged, check=True, timeout=timeout_seconds)
        finally:
            # This check also runs after TimeoutExpired or CalledProcessError;
            # the staging tree is discarded in all failure cases.
            if repository_digest(repo) != live_before:
                raise RuntimeError(
                    "Live repository changed during staged compilation; "
                    "discarding candidate without overwriting live edits"
                )

        reject_symlinks(staged)
        after = repository_digest(staged)
        validate_model_changes(before, after)
        apply_staged_changes(repo, staged, live_before, before, after)


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
