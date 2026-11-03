"""Review-first, local-only knowledge change bundles.

ARCH-00C is a file-level safety bridge, not semantic Claim/Evidence review.
Nothing here runs Git or calls a model. Candidate and private approval data live
under gitignored .state/; publication needs a *separate* explicit promotion.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from compile_transaction import apply_transaction, durable_json, safe_sync_dir, verify_path
from staged_workspace import (
    atomic_replace_file,
    changed_paths,
    repository_digest,
    stage_source_tree,
    validate_model_changes,
)
from wiki_lint import lint_wiki

HEX_SHA = re.compile(r"^[0-9a-f]{64}$")
VERSION = 1


def _hash(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def _canonical(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _state_root(repo: Path, name: str) -> Path:
    repo = repo.resolve()
    state = repo / ".state"
    root = state / name
    if state.is_symlink() or root.is_symlink():
        raise RuntimeError("Symlinked private state is forbidden")
    state.mkdir(mode=0o700, exist_ok=True)
    root.mkdir(mode=0o700, exist_ok=True)
    return root


def _bundle_path(repo: Path, identifier: str, *, approved: bool = False) -> Path:
    if not HEX_SHA.fullmatch(identifier):
        raise ValueError("candidate ID must be a full SHA-256 digest")
    path = _state_root(repo, "approved-knowledge" if approved else "review-candidates")
    result = path / identifier
    if result.is_symlink():
        raise RuntimeError("Symlinked candidate directory is forbidden")
    return result


def _write_private(path: Path, payload: bytes) -> None:
    with path.open("xb") as stream:
        os.chmod(path, 0o600)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _read_bundle(repo: Path, candidate_id: str, *, approved: bool = False) -> dict:
    directory = _bundle_path(repo, candidate_id, approved=approved)
    if not directory.is_dir() or directory.is_symlink():
        raise FileNotFoundError("review candidate does not exist")
    manifest_path = directory / "candidate.json"
    if manifest_path.is_symlink():
        raise RuntimeError("Symlinked candidate manifest is forbidden")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or set(manifest) != {"version", "sources", "changes"}:
        raise RuntimeError("invalid private candidate manifest")
    if manifest["version"] != VERSION or not isinstance(manifest["sources"], list):
        raise RuntimeError("unsupported candidate format")
    if _hash(_canonical(manifest)) != candidate_id:
        raise RuntimeError("private candidate manifest fingerprint mismatch")
    changes = manifest["changes"]
    if not isinstance(changes, list) or not changes:
        raise RuntimeError("candidate has no changed knowledge content")
    seen: set[str] = set()
    for change in changes:
        if not isinstance(change, dict) or set(change) != {"path", "before", "after"}:
            raise RuntimeError("invalid candidate change entry")
        path = change["path"]
        if not isinstance(path, str) or path in seen:
            raise RuntimeError("invalid or duplicate candidate path")
        seen.add(path)
        verify_path(repo, path)
        for key in ("before", "after"):
            value = change[key]
            if value is not None and (not isinstance(value, str) or not HEX_SHA.fullmatch(value)):
                raise RuntimeError("invalid candidate file digest")
        if change["after"] is not None:
            blob = directory / "blobs" / change["after"]
            if blob.is_symlink() or not blob.is_file() or _hash(blob.read_bytes()) != change["after"]:
                raise RuntimeError("candidate blob missing or damaged")
    return manifest


def capture_candidate(
    repo: Path,
    staged: Path,
    before: dict[str, str],
    after: dict[str, str],
    sources: list[Path],
) -> str | None:
    """Persist validated model changes WITHOUT touching the public tree."""
    validate_model_changes(before, after)
    changes = changed_paths(before, after)
    if not changes:
        return None
    rows: list[dict[str, str | None]] = []
    payloads: dict[str, bytes] = {}
    for relative in changes:
        verify_path(repo, relative)
        desired = (staged / relative).read_bytes() if relative in after else None
        digest = _hash(desired)
        rows.append({"path": relative, "before": before.get(relative), "after": digest})
        if desired is not None and digest is not None:
            payloads[digest] = desired
    manifest = {
        "version": VERSION,
        "sources": sorted(path.as_posix() for path in sources),
        "changes": rows,
    }
    candidate_id = _hash(_canonical(manifest))
    assert candidate_id is not None
    destination = _bundle_path(repo, candidate_id)
    if destination.exists():
        _read_bundle(repo, candidate_id)
        return candidate_id

    root = destination.parent
    temporary = Path(tempfile.mkdtemp(prefix=".candidate-", dir=root))
    os.chmod(temporary, 0o700)
    try:
        blob_root = temporary / "blobs"
        blob_root.mkdir(mode=0o700)
        for digest, payload in payloads.items():
            _write_private(blob_root / digest, payload)
        _write_private(temporary / "candidate.json", _canonical(manifest))
        safe_sync_dir(blob_root)
        safe_sync_dir(temporary)
        if destination.exists():
            _read_bundle(repo, candidate_id)
        else:
            os.replace(temporary, destination)
            safe_sync_dir(root)
            temporary = None
    finally:
        if temporary is not None and temporary.exists():
            shutil.rmtree(temporary)
    return candidate_id


def _check_public_base(repo: Path, manifest: dict) -> None:
    for item in manifest["changes"]:
        live = verify_path(repo, item["path"])
        if _hash(live.read_bytes() if live.exists() else None) != item["before"]:
            raise RuntimeError("knowledge changed since candidate generation; regenerate")


def review_preview(repo: Path, candidate_id: str) -> tuple[str, str]:
    """Generate human-readable local diff. It may include PRIVATE CONTENT."""
    manifest = _read_bundle(repo, candidate_id)
    _check_public_base(repo, manifest)
    directory = _bundle_path(repo, candidate_id)
    parts: list[str] = []
    for change in manifest["changes"]:
        path = change["path"]
        current = verify_path(repo, path)
        old = current.read_text(encoding="utf-8").splitlines(keepends=True) if current.exists() else []
        new = (
            (directory / "blobs" / change["after"]).read_text(encoding="utf-8").splitlines(
                keepends=True
            )
            if change["after"] else []
        )
        parts.extend(difflib.unified_diff(old, new, fromfile="before/" + path, tofile="after/" + path))
    public_sha = hashlib.sha256(
        _canonical({"action": "public-promotion", "candidate": candidate_id})
    ).hexdigest()
    return "".join(parts), public_sha


def approve_private(repo: Path, candidate_id: str, *, confirmation: str) -> Path:
    """Explicit local approval. Does NOT modify wiki/ or any public file."""
    if confirmation != candidate_id:
        raise PermissionError("private approval requires full candidate SHA confirmation")
    _read_bundle(repo, candidate_id)
    _check_public_base(repo, _read_bundle(repo, candidate_id))
    src = _bundle_path(repo, candidate_id)
    dest = _bundle_path(repo, candidate_id, approved=True)
    if dest.exists():
        _read_bundle(repo, candidate_id, approved=True)
        return dest

    tmp = Path(tempfile.mkdtemp(prefix=".approval-", dir=dest.parent))
    os.chmod(tmp, 0o700)
    try:
        shutil.copytree(src / "blobs", tmp / "blobs")
        shutil.copy2(src / "candidate.json", tmp / "candidate.json")
        for path in tmp.rglob("*"):
            if path.is_file():
                path.chmod(0o600)
        _read_blob_manifest = json.loads((tmp / "candidate.json").read_text(encoding="utf-8"))
        if _hash(_canonical(_read_blob_manifest)) != candidate_id:
            raise RuntimeError("candidate changed during private approval")
        os.replace(tmp, dest)
        safe_sync_dir(dest.parent)
        tmp = None
    finally:
        if tmp is not None and tmp.exists():
            shutil.rmtree(tmp)
    _read_bundle(repo, candidate_id, approved=True)
    return dest


def promote_public(repo: Path, candidate_id: str, *, confirmation: str) -> list[str]:
    """Separate public-worktree promotion; never commits or pushes to Git.

    Requires the explicit public-preview digest. The compiled Wiki is linted
    in a fresh staging workspace BEFORE the first public file is changed.
    """
    repo = repo.resolve()
    manifest = _read_bundle(repo, candidate_id, approved=True)
    expected = hashlib.sha256(
        _canonical({"action": "public-promotion", "candidate": candidate_id})
    ).hexdigest()
    if confirmation != expected:
        raise PermissionError("public promotion requires the separate preview fingerprint")
    _check_public_base(repo, manifest)

    with tempfile.TemporaryDirectory(prefix="xwiki-publish-preview-") as directory:
        stage = Path(directory)
        stage_source_tree(repo, stage)
        source = _bundle_path(repo, candidate_id, approved=True)
        desired: dict[str, bytes | None] = {}
        for item in manifest["changes"]:
            relative = item["path"]
            value = (
                (source / "blobs" / item["after"]).read_bytes()
                if item["after"] is not None else None
            )
            target = stage / relative
            if value is None:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(value)
            desired[relative] = value
        errors = [finding for finding in lint_wiki(stage) if finding.severity == "error"]
        if errors:
            raise RuntimeError(
                "public preview failed lint: "
                + ", ".join(item.code for item in errors[:6])
            )
        snapshot = repository_digest(repo)
        _check_public_base(repo, manifest)
        record_path = _state_root(repo, "public-promotions") / (candidate_id + ".json")
        durable_json(
            record_path,
            {"candidate": candidate_id, "changes": sorted(desired),
             "public_fingerprint": expected, "state": "prepared"},
        )
        result = apply_transaction(
            repo, desired, write=atomic_replace_file, expected_snapshot=snapshot
        )
    # Local public export only: never commits or pushes Git. The intent must
    # be durably recorded before any public file mutation; a failed apply leaves
    # a prepared marker for an operator to reconcile with compile journal.
    durable_json(
        record_path,
        {"candidate": candidate_id, "changes": result, "public_fingerprint": expected,
         "state": "applied_locally"},
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explicit local X-Wiki review workflow")
    parser.add_argument("action", choices=("show", "approve", "promote"))
    parser.add_argument("candidate", help="full 64-character private candidate ID")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--confirm", help="for approve: repeat the candidate SHA")
    parser.add_argument("--confirm-public", help="for promote: use the separate public digest")
    args = parser.parse_args(argv)
    repo = args.repo.expanduser().resolve()
    if args.action == "show":
        diff, fingerprint = review_preview(repo, args.candidate)
        print(diff)
        print("PUBLIC_PROMOTION_FINGERPRINT=" + fingerprint)
    elif args.action == "approve":
        approve_private(repo, args.candidate, confirmation=args.confirm or "")
        print("Approved to private knowledge only; no Git files changed.")
    else:
        changed = promote_public(repo, args.candidate, confirmation=args.confirm_public or "")
        print("Promoted locally for separate Git publication:", ", ".join(changed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
