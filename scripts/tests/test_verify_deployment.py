"""Public Pages read-back verifies actual HTTP content, not just Git pushes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from release_gate import ReleaseManifest
from verify_deployment import (
    canonical_site_url,
    download_public_manifest,
    normalized_site_url,
    verify_live_release,
)


def fixture(tmp_path: Path) -> tuple[Path, ReleaseManifest]:
    (tmp_path / "mkdocs.yml").write_text(
        "site_url: https://example.github.io/X-Wiki/\n", encoding="utf-8"
    )
    manifest = ReleaseManifest(
        schema_version=1,
        commit_sha="a" * 40,
        content_sha256="b" * 64,
        files=(
            {"path": "index.md", "git_blob_sha": "c" * 40},
            {"path": "wiki/concepts/topic.md", "git_blob_sha": "d" * 40},
        ),
    )
    return tmp_path, manifest


def live_document(m: ReleaseManifest) -> dict:
    return {
        "schema_version": m.schema_version,
        "commit_sha": m.commit_sha,
        "content_sha256": m.content_sha256,
        "files": list(m.files),
    }


def test_canonical_url_rejects_wrong_host_path_and_http(tmp_path: Path) -> None:
    repo, _ = fixture(tmp_path)
    canonical = canonical_site_url(repo)
    assert normalized_site_url("https://example.github.io/X-Wiki", canonical) == canonical
    for bad in (
        "http://example.github.io/X-Wiki/",
        "https://evil.example/X-Wiki/",
        "https://example.github.io/",
        "https://example.github.io/X-Wiki/?trick=1",
    ):
        with pytest.raises(ValueError, match="configured HTTPS"):
            normalized_site_url(bad, canonical)


def test_exact_live_manifest_returns_deployment_receipt(tmp_path: Path) -> None:
    repo, manifest = fixture(tmp_path)
    captured: list[str] = []

    def fake_fetch(url: str) -> dict:
        captured.append(url)
        return live_document(manifest)

    receipt = verify_live_release(
        repo,
        "https://example.github.io/X-Wiki/",
        manifest,
        max_wait_seconds=0,
        fetch=fake_fetch,
    )
    assert receipt["commit_sha"] == manifest.commit_sha
    assert receipt["content_sha256"] == manifest.content_sha256
    assert receipt["verification"] == "https-manifest-readback"
    assert len(captured) == 1
    assert "/release-manifest.json?verify=" in captured[0]


def test_stale_release_must_not_be_marked_deployed(tmp_path: Path) -> None:
    repo, manifest = fixture(tmp_path)
    stale = live_document(manifest)
    stale["commit_sha"] = "0" * 40
    with pytest.raises(RuntimeError, match="not verified"):
        verify_live_release(
            repo,
            "https://example.github.io/X-Wiki/",
            manifest,
            max_wait_seconds=0,
            fetch=lambda _: stale,
        )


def test_transient_stale_page_recovers_on_second_read(tmp_path: Path) -> None:
    repo, manifest = fixture(tmp_path)
    calls = 0

    def fake_fetch(_: str) -> dict:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"commit_sha": "stale"}
        return live_document(manifest)

    clock = iter([0.0, 0.0])
    receipt = verify_live_release(
        repo,
        "https://example.github.io/X-Wiki/",
        manifest,
        max_wait_seconds=20,
        fetch=fake_fetch,
        sleep=lambda _: None,
        monotonic=lambda: next(clock),
    )
    assert receipt["attempts"] == 2


def test_limit_manifest_response_size_and_cross_origin_redirect() -> None:
    class Response:
        def __init__(self, payload: bytes, url: str) -> None:
            self.payload = payload
            self.url = url

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self, count: int) -> bytes:
            return self.payload[:count]

        def geturl(self) -> str:
            return self.url

    url = "https://example.github.io/X-Wiki/release-manifest.json"
    with pytest.raises(RuntimeError, match="redirected"):
        download_public_manifest(
            url, opener=lambda *_a, **_k: Response(b"{}", "https://other.example/x")
        )
    with pytest.raises(RuntimeError, match="size limit"):
        download_public_manifest(
            url, opener=lambda *_a, **_k: Response(b"x" * 1_000_002, url)
        )


def test_bad_json_is_not_accepted(tmp_path: Path) -> None:
    repo, manifest = fixture(tmp_path)
    with pytest.raises(RuntimeError, match="not verified"):
        verify_live_release(
            repo,
            "https://example.github.io/X-Wiki/",
            manifest,
            max_wait_seconds=0,
            fetch=lambda _: json.loads('"not a manifest"'),
        )
