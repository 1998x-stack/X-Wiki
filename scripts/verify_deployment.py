#!/usr/bin/env python3
"""Verify the live public Pages release manifest before issuing a receipt."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from release_gate import ReleaseManifest, atomic_json, build_manifest

MAX_RESPONSE_BYTES = 1_000_000


def canonical_site_url(repo: Path) -> str:
    for line in (repo / "mkdocs.yml").read_text(encoding="utf-8").splitlines():
        if line.startswith("site_url:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    raise RuntimeError("site_url is missing from mkdocs.yml")


def normalized_site_url(site_url: str, expected_url: str) -> str:
    site = urllib.parse.urlsplit(site_url)
    expected = urllib.parse.urlsplit(expected_url)
    if (
        site.scheme != "https"
        or site.username is not None
        or site.password is not None
        or site.hostname != expected.hostname
        or site.port != expected.port
        or site.path.rstrip("/") != expected.path.rstrip("/")
        or site.query
        or site.fragment
    ):
        raise ValueError("Deployment URL differs from the configured HTTPS site_url")
    return site_url.rstrip("/") + "/"


def download_public_manifest(
    url: str,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "X-Wiki-release-verify/1",
        },
    )
    with opener(request, timeout=10) as response:
        final_url = urllib.parse.urlsplit(response.geturl())
        original_url = urllib.parse.urlsplit(url)
        if final_url.scheme != "https" or final_url.hostname != original_url.hostname:
            raise RuntimeError("Manifest request redirected outside HTTPS site origin")
        payload = response.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            raise RuntimeError("Live release manifest exceeded the size limit")
    document = json.loads(payload.decode("utf-8"))
    if not isinstance(document, dict):
        raise RuntimeError("Live release manifest was not a JSON object")
    return document


def verify_live_release(
    repo: Path,
    site_url: str,
    manifest: ReleaseManifest,
    *,
    max_wait_seconds: float,
    fetch: Callable[[str], dict[str, Any]] = download_public_manifest,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Only return success after exact SHA and file manifest read-back."""
    root = normalized_site_url(site_url, canonical_site_url(repo))
    # A unique query lets CDN caches serve the newly deployed revision.
    url = root + "release-manifest.json?verify=" + manifest.commit_sha
    started = monotonic()
    attempts = 0
    last_error = "not checked"
    while True:
        attempts += 1
        try:
            live = fetch(url)
            if not isinstance(live, dict):
                raise ValueError("Live release manifest is not a JSON object")
            if (
                live.get("schema_version") == manifest.schema_version
                and live.get("commit_sha") == manifest.commit_sha
                and live.get("content_sha256") == manifest.content_sha256
                and live.get("files") == list(manifest.files)
            ):
                return {
                    "schema_version": 1,
                    "verification": "https-manifest-readback",
                    "site_url": root,
                    "commit_sha": manifest.commit_sha,
                    "content_sha256": manifest.content_sha256,
                    "verified_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "attempts": attempts,
                    "run_id": os.environ.get("GITHUB_RUN_ID"),
                }
            last_error = "live manifest does not match the expected commit and files"
        except (
            urllib.error.URLError,
            OSError,
            UnicodeError,
            ValueError,
            RuntimeError,
        ) as error:
            last_error = type(error).__name__
        elapsed = monotonic() - started
        remaining = max_wait_seconds - elapsed
        if remaining <= 0:
            raise RuntimeError(
                "GitHub Pages deployment not verified; "
                f"{attempts} read-back attempt(s), last result: {last_error}"
            )
        sleep(min(5.0, remaining))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--site-url", required=True)
    parser.add_argument("--max-wait", type=float, default=180.0)
    parser.add_argument("--receipt", type=Path, default=Path("deployment-receipt.json"))
    args = parser.parse_args()
    if not (0 <= args.max_wait <= 600):
        parser.error("--max-wait must be between 0 and 600 seconds")
    repo = args.repo.resolve()
    receipt = verify_live_release(
        repo,
        args.site_url,
        build_manifest(repo),
        max_wait_seconds=args.max_wait,
    )
    atomic_json(args.receipt, receipt)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
