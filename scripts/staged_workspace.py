"""Prepare and validate disposable knowledge compilation workspaces.

This is a defense-in-depth staging mechanism, not a process sandbox. It
prevents ordinary partial Agent edits from corrupting live wiki files.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path

ALLOWED_OUTPUTS = {"index.md", "log.md"}
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
    """Hash repository files, excluding known generated or private state."""
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


def changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(
        path for path in before.keys() | after.keys() if before.get(path) != after.get(path)
    )


def validate_model_changes(before: dict[str, str], after: dict[str, str]) -> None:
    invalid = [
        path
        for path in changed_paths(before, after)
        if path not in ALLOWED_OUTPUTS and not path.startswith("wiki/")
    ]
    if invalid:
        raise RuntimeError(
            f"wiki compiler changed files outside its boundary: {', '.join(invalid)}"
        )


def reject_symlinks(root: Path) -> None:
    """Do not follow model-created symlinks outside the staging tree."""
    if root.is_symlink():
        raise RuntimeError(f"symlink is not allowed in compile workspace: {root}")
    for current, directories, files in os.walk(root, followlinks=False):
        for name in directories + files:
            path = Path(current) / name
            if path.is_symlink():
                raise RuntimeError(
                    f"symlink is not allowed in compile workspace: {path.relative_to(root)}"
                )


def stage_source_tree(repo: Path, staged: Path) -> None:
    """Copy only the raw evidence, knowledge layer, and compiler instructions."""
    for name in ("raw", "wiki"):
        source = repo / name
        if not source.is_dir():
            raise FileNotFoundError(f"required directory not found: {source}")
        reject_symlinks(source)
        shutil.copytree(source, staged / name, symlinks=True)
    for name in ("index.md", "log.md"):
        source = repo / name
        if source.is_symlink():
            raise RuntimeError(f"symlink is not allowed: {source}")
        if source.is_file():
            shutil.copy2(source, staged / name)
    source_skill = repo / "scripts" / "skills" / "x-wiki-compiler"
    reject_symlinks(source_skill)
    shutil.copytree(source_skill, staged / "scripts" / "skills" / "x-wiki-compiler")
    reject_symlinks(staged)


def atomic_replace_file(path: Path, payload: bytes) -> None:
    """Replace one regular file atomically, preserving its existing mode."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.is_file() else 0o644
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.chmod(mode)
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def apply_staged_changes(
    repo: Path,
    staged: Path,
    live_before: dict[str, str],
    staged_before: dict[str, str],
    staged_after: dict[str, str],
) -> list[str]:
    """Apply validated changes, rolling back earlier writes on failure.

    Multi-file replacement is not globally atomic. Failure rollback is
    best-effort; filesystem errors during rollback require manual recovery.
    """
    validate_model_changes(staged_before, staged_after)
    reject_symlinks(staged)
    if repository_digest(repo) != live_before:
        raise RuntimeError("Live repository changed before applying staged output")

    changes = changed_paths(staged_before, staged_after)
    backups: dict[str, bytes | None] = {}
    for relative in changes:
        live = repo / relative
        if live.is_symlink() or (live.exists() and not live.is_file()):
            raise RuntimeError(f"unsafe live destination: {relative}")
        backups[relative] = live.read_bytes() if live.is_file() else None

    try:
        for relative in changes:
            candidate = staged / relative
            live = repo / relative
            if candidate.is_file():
                atomic_replace_file(live, candidate.read_bytes())
            else:
                live.unlink(missing_ok=True)
    except Exception:
        rollback_errors: list[str] = []
        for relative, payload in backups.items():
            live = repo / relative
            try:
                if payload is None:
                    live.unlink(missing_ok=True)
                else:
                    atomic_replace_file(live, payload)
            except OSError as error:
                rollback_errors.append(f"{relative}: {error}")
        if rollback_errors:
            raise RuntimeError(
                "Compilation apply failed AND rollback was incomplete: "
                + "; ".join(rollback_errors)
            ) from None
        raise
    return changes
