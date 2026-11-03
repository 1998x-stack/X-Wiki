"""Durable, recoverable multi-file Wiki writeback with conflict detection.

A prepared journal is fsynced *before* the first knowledge-file edit. If
interrupted, the next ingestion run restores only files whose contents are
one of the recorded before/after revisions. Divergent manual changes abort
recovery instead of being overwritten.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import shutil
import tempfile
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

JOURNAL_VERSION = 1


def digest(payload: bytes | None) -> str | None:
    return hashlib.sha256(payload).hexdigest() if payload is not None else None


def verify_path(repo: Path, relative: str) -> Path:
    path = Path(relative)
    if (
        path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or not (
            relative in {"index.md", "log.md"}
            or (relative.startswith("wiki/") and relative.endswith(".md"))
        )
    ):
        raise RuntimeError(f"Unsafe compilation journal path: {relative}")
    live = repo / path
    for ancestor in (live, *live.parents):
        if ancestor == repo.parent:
            break
        if ancestor.is_symlink():
            raise RuntimeError(f"Symlinked compilation path: {relative}")
    if live.exists() and not live.is_file():
        raise RuntimeError(f"Non-file compilation destination: {relative}")
    return live


def safe_sync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        try:
            os.fsync(fd)
        except OSError as error:
            # Some OS/filesystems do not support fsync() on a directory.
            if error.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP}:
                raise
    finally:
        os.close(fd)


def durable_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=".journal-",
            mode="w",
            encoding="utf-8",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, sort_keys=True, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
        temporary = None
        safe_sync_dir(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def durable_backup(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("xb") as handle:
        os.chmod(path, 0o600)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    safe_sync_dir(path.parent)


def transactions_root(repo: Path) -> Path:
    return repo / ".state" / "compile-transactions"


@contextmanager
def exclusive_compile_lock(repo: Path) -> Iterator[None]:
    lock = repo / ".state" / "compile.lock"
    if lock.parent.is_symlink():
        raise RuntimeError("Symlinked compilation state directory")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _recover_unlocked(
    repo: Path,
    *,
    write: Callable[[Path, bytes], None],
) -> list[str]:
    root = transactions_root(repo)
    if not root.exists():
        return []
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("Unsafe compilation transaction directory")
    restored: list[str] = []
    for transaction in sorted(root.iterdir()):
        if transaction.is_symlink() or not transaction.is_dir():
            raise RuntimeError(f"Unexpected compile transaction entry: {transaction}")
        journal = transaction / "journal.json"
        if not journal.is_file() or journal.is_symlink():
            # An incomplete preparation is harmless: apply never starts
            # before the complete journal is persisted.
            shutil.rmtree(transaction)
            continue
        record = json.loads(journal.read_text(encoding="utf-8"))
        if record.get("version") != JOURNAL_VERSION:
            raise RuntimeError("Unsupported compilation journal format")
        state = record.get("state")
        if state == "committed":
            shutil.rmtree(transaction)
            continue
        if state != "prepared":
            raise RuntimeError(f"Unknown compilation journal state: {state}")
        items = record.get("files")
        if not isinstance(items, list):
            raise RuntimeError("Corrupt compilation transaction files")
        checked: list[tuple[Path, bytes | None, str]] = []
        for i, item in enumerate(items):
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                raise RuntimeError("Corrupt compilation transaction entry")
            relative = item["path"]
            live = verify_path(repo, relative)
            original_sha = item.get("before")
            expected_sha = item.get("after")
            original = None
            if original_sha is not None:
                backup = transaction / "backups" / str(i)
                if backup.is_symlink() or not backup.is_file():
                    raise RuntimeError(f"Missing compilation rollback backup: {relative}")
                original = backup.read_bytes()
                if digest(original) != original_sha:
                    raise RuntimeError(f"Corrupt compilation rollback backup: {relative}")
            current = live.read_bytes() if live.exists() else None
            if digest(current) not in {original_sha, expected_sha}:
                raise RuntimeError(
                    "Manual edit conflicts with interrupted compilation: "
                    + relative
                )
            checked.append((live, original, relative))
        # Prevalidate every path and its current content before restoring
        # anything, so one conflict never partly overwrites manual edits.
        for live, original, relative in checked:
            if original is None:
                live.unlink(missing_ok=True)
            else:
                write(live, original)
            safe_sync_dir(live.parent)
            restored.append(relative)
        shutil.rmtree(transaction)
    return restored


def recover_transactions(
    repo: Path, *, write: Callable[[Path, bytes], None] | None = None
) -> list[str]:
    if write is None:
        from staged_workspace import atomic_replace_file
        write = atomic_replace_file
    with exclusive_compile_lock(repo):
        return _recover_unlocked(repo, write=write)


def apply_transaction(
    repo: Path,
    changes: dict[str, bytes | None],
    *,
    write: Callable[[Path, bytes], None],
    expected_snapshot: dict[str, str] | None = None,
) -> list[str]:
    """Apply staged candidate, backed by a durable recovery journal."""
    if not changes:
        return []
    with exclusive_compile_lock(repo):
        restored = _recover_unlocked(repo, write=write)
        if restored:
            raise RuntimeError(
                "Recovered previous interrupted compilation; retry with fresh snapshot"
            )
        if expected_snapshot is not None:
            from staged_workspace import repository_digest

            if repository_digest(repo) != expected_snapshot:
                raise RuntimeError(
                    "Live repository changed before the compilation write lock"
                )
        root = transactions_root(repo)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if root.is_symlink():
            raise RuntimeError("Unsafe transaction root")
        transaction = root / uuid.uuid4().hex
        transaction.mkdir(mode=0o700)
        rows: list[dict[str, str | None]] = []
        for i, (relative, desired) in enumerate(sorted(changes.items())):
            live = verify_path(repo, relative)
            before = live.read_bytes() if live.exists() else None
            if before is not None:
                durable_backup(transaction / "backups" / str(i), before)
            rows.append({
                "path": relative,
                "before": digest(before),
                "after": digest(desired),
            })
        safe_sync_dir(transaction)
        record = {"version": JOURNAL_VERSION, "state": "prepared", "files": rows}
        durable_json(transaction / "journal.json", record)
        try:
            for relative, desired in sorted(changes.items()):
                live = verify_path(repo, relative)
                if desired is None:
                    live.unlink(missing_ok=True)
                else:
                    write(live, desired)
                safe_sync_dir(live.parent)
        except Exception:
            # Keep the on-disk journal if rollback fails; a later scan
            # will retry without overwriting unrelated user changes.
            _recover_unlocked(repo, write=write)
            raise
        record["state"] = "committed"
        durable_json(transaction / "journal.json", record)
        shutil.rmtree(transaction)
        return sorted(changes)
