#!/usr/bin/env python3
"""Crash-recoverable Git release journal for public Wiki knowledge commits.

A confirmed Git remote ref is NOT the same as successful GitHub Pages deployment.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ReleaseManifest:
    """Deterministic manifest of committed public knowledge files."""

    schema_version: int
    commit_sha: str
    content_sha256: str
    files: tuple[dict[str, str], ...]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def build_manifest(repo: Path) -> ReleaseManifest:
    """Hash the actual Git HEAD tree, never uncommitted or private raw sources."""
    commit_sha = git(repo, "rev-parse", "--verify", "HEAD")
    tree = subprocess.run(
        ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD", "--",
         "wiki", "index.md", "log.md"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout
    files: list[dict[str, str]] = []
    for record in tree.split(b"\0"):
        if not record:
            continue
        metadata, sep, path_bytes = record.partition(b"\t")
        if not sep:
            raise RuntimeError("Malformed git tree entry")
        mode, kind, object_id = metadata.decode("ascii").split()
        path = path_bytes.decode("utf-8")
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise RuntimeError(f"Unsafe non-regular public file: {path}")
        if not (path in {"index.md", "log.md"} or path.startswith("wiki/")):
            raise RuntimeError(f"Unexpected release path: {path}")
        files.append({"path": path, "git_blob_sha": object_id})
    files.sort(key=lambda item: item["path"])
    if not {"index.md", "log.md"}.issubset({item["path"] for item in files}):
        raise RuntimeError("Knowledge manifest requires index.md and log.md")
    if not any(item["path"].startswith("wiki/") for item in files):
        raise RuntimeError("Knowledge manifest requires at least one wiki page")
    fingerprint = hashlib.sha256()
    for item in files:
        fingerprint.update(item["path"].encode("utf-8"))
        fingerprint.update(b"\0")
        fingerprint.update(item["git_blob_sha"].encode("ascii"))
        fingerprint.update(b"\n")
    return ReleaseManifest(
        schema_version=SCHEMA_VERSION,
        commit_sha=commit_sha,
        content_sha256=fingerprint.hexdigest(),
        files=tuple(files),
    )


def _journal_path(repo: Path, commit: str, remote: str, branch: str) -> Path:
    key = hashlib.sha256(f"{remote}\0{branch}".encode("utf-8")).hexdigest()[:16]
    return repo / ".state" / "releases" / f"{commit}-{key}.json"


def atomic_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{path.name}.",
            dir=path.parent,
            delete=False,
        ) as handle:
            candidate = Path(handle.name)
            json.dump(document, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(candidate, 0o600)
        os.replace(candidate, path)
        candidate = None
        if hasattr(os, "O_DIRECTORY"):
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if candidate is not None:
            candidate.unlink(missing_ok=True)


def record_release(
    repo: Path,
    manifest: ReleaseManifest,
    remote: str,
    branch: str,
    status: str,
) -> Path:
    """Persist state without storing source text, credentials or remote URLs."""
    if status not in {"prepared", "git_confirmed"}:
        raise ValueError(f"unknown publication state: {status}")
    path = _journal_path(repo, manifest.commit_sha, remote, branch)
    document = {
        "manifest": asdict(manifest),
        "remote": remote,
        "branch": branch,
        "status": status,
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    atomic_json(path, document)
    return path


def remote_head(repo: Path, remote: str, branch: str) -> str | None:
    ref = f"refs/heads/{branch}"
    output = git(repo, "ls-remote", "--heads", remote, ref)
    if not output:
        return None
    rows = [line.split("\t") for line in output.splitlines()]
    exact = [row[0] for row in rows if len(row) == 2 and row[1] == ref]
    if len(exact) != 1:
        raise RuntimeError("Could not uniquely verify remote branch head")
    return exact[0]


def publish_head(repo: Path, remote: str, branch: str) -> ReleaseManifest:
    """Journal before network I/O, verify the remote, then confirm success.

    If interrupted after a successful push, retry checks the remote and
    finalizes the same manifest without pushing a second content change.
    """
    if not remote or not branch:
        raise ValueError("remote and branch must be set")
    git(repo, "check-ref-format", "--branch", branch)
    manifest = build_manifest(repo)
    record_release(repo, manifest, remote, branch, "prepared")
    if remote_head(repo, remote, branch) != manifest.commit_sha:
        subprocess.run(
            ["git", "push", remote, f"HEAD:refs/heads/{branch}"],
            cwd=repo,
            check=True,
        )
    if remote_head(repo, remote, branch) != manifest.commit_sha:
        raise RuntimeError("Remote ref differs from pushed commit; keeping publication pending")
    if git(repo, "rev-parse", "--verify", "HEAD") != manifest.commit_sha:
        raise RuntimeError("Local HEAD changed during publication; retry after reconciliation")
    record_release(repo, manifest, remote, branch, "git_confirmed")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect public Git release manifest")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    manifest = build_manifest(args.repo.expanduser().resolve())
    print(json.dumps(asdict(manifest), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
