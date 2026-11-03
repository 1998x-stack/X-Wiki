"""UX-002A: real files, private blobs, integrity and failure recovery tests."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from xwiki.application.import_source import ImportSource
from xwiki.domain.enums import SourceOrigin, SourceStatus
from xwiki.infrastructure.file_store import BlobError, PrivateBlobStore
from xwiki.infrastructure.sqlite.database import open_product_db
from xwiki.infrastructure.sqlite.repositories import ProductRepository
from xwiki.interfaces.import_cli import main


@pytest.fixture
def stores(tmp_path: Path):
    connection = open_product_db(tmp_path / ".state" / "product.sqlite")
    blobs = PrivateBlobStore(tmp_path / ".state" / "source-store")
    try:
        yield ProductRepository(connection), blobs
    finally:
        connection.close()


def test_text_import_is_durable_and_private_after_reopen(
    tmp_path: Path, stores
) -> None:
    repo, blob = stores
    source = tmp_path / "personal.md"
    original = "# 我的观点\n它曾经改变过。🙂\n".encode()
    source.write_bytes(original)
    outcome = ImportSource(repo, blob).execute(source)
    assert outcome.duplicate is False
    assert outcome.source.status is SourceStatus.STORED
    assert outcome.source.origin is SourceOrigin.FILE
    assert outcome.blob.size_bytes == len(original)
    assert blob.read_verified(outcome.source.content_sha256) == original
    assert source.read_bytes() == original
    target = blob._blob_path(outcome.source.content_sha256)
    assert target.read_bytes() == original
    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
        assert stat.S_IMODE(blob.root.stat().st_mode) == 0o700
    with open_product_db(tmp_path / ".state" / "product.sqlite") as second:
        saved = ProductRepository(second).get_source(outcome.source.source_id)
        assert saved == outcome.source
        assert blob.verify_blob(saved.content_sha256) == len(original)


def test_duplicate_input_is_idempotent_and_keeps_original_timestamp(
    tmp_path: Path, stores
) -> None:
    repo, blob = stores
    first_file = tmp_path / "one.txt"
    second_file = tmp_path / "two.md"
    first_file.write_text("Repeated original note.\n", encoding="utf-8")
    second_file.write_text("Repeated original note.\n", encoding="utf-8")
    first = ImportSource(repo, blob).execute(first_file)
    second = ImportSource(repo, blob).execute(second_file)
    assert second.duplicate is True
    assert second.source == first.source
    assert repo.connection.execute("SELECT count(*) FROM sources").fetchone()[0] == 1


def test_same_filename_different_bytes_is_a_distinct_source(
    tmp_path: Path, stores
) -> None:
    repo, blob = stores
    file = tmp_path / "note.txt"
    file.write_text("First version")
    first = ImportSource(repo, blob).execute(file)
    file.write_text("Second version")
    second = ImportSource(repo, blob).execute(file)
    assert first.source.source_id != second.source.source_id
    assert blob.read_verified(first.source.content_sha256) == b"First version"


@pytest.mark.parametrize(
    "suffix,contents",
    [
        (".m4a", b"\x00\x00\x00\x18ftypisom" + b"\x00" * 8),
        (".wav", b"RIFF\x08\x00\x00\x00WAVEfmt "),
        (".mp3", b"ID3\x04\x00\x00\x00\x00\x00\x00"),
    ],
)
def test_audio_import_saves_bytes_without_transcription(
    tmp_path: Path, stores, suffix: str, contents: bytes
) -> None:
    repo, blob = stores
    file = tmp_path / ("audio" + suffix)
    file.write_bytes(contents)
    result = ImportSource(repo, blob).execute(file)
    assert result.blob.media_kind == "audio"
    assert result.source.status is SourceStatus.STORED
    assert blob.read_verified(result.source.content_sha256) == contents


@pytest.mark.parametrize(
    "suffix,contents",
    [
        (".txt", b"\xff\xfehello"),
        (".pdf", b"%PDF-1.4"),
        (".m4a", b"not a real ISO header"),
        (".wav", b"RIFFgarbage!"),
        (".mp3", b"not an MP3 header"),
        (".md", b""),
    ],
)
def test_unsupported_or_corrupt_inputs_never_become_stored(
    tmp_path: Path, stores, suffix: str, contents: bytes
) -> None:
    repo, blob = stores
    file = tmp_path / ("bad" + suffix)
    file.write_bytes(contents)
    with pytest.raises(BlobError):
        ImportSource(repo, blob).execute(file)
    assert repo.connection.execute("SELECT count(*) FROM sources").fetchone()[0] == 0


def test_symlinked_user_file_is_rejected(tmp_path: Path, stores) -> None:
    repo, blob = stores
    real = tmp_path / "real.md"
    real.write_text("private content")
    alias = tmp_path / "alias.md"
    alias.symlink_to(real)
    with pytest.raises(BlobError, match="symlink"):
        ImportSource(repo, blob).execute(alias)
    assert repo.connection.execute("SELECT count(*) FROM sources").fetchone()[0] == 0


def test_input_changed_mid_copy_leaves_no_stored_source(tmp_path: Path, stores) -> None:
    repo, blob = stores
    source = tmp_path / "changing.md"
    source.write_text("Before change")

    def rewrite(_count: int) -> None:
        source.write_text("I changed while importing")

    with pytest.raises(BlobError, match="changed"):
        blob.put_file(source, on_chunk=rewrite)
    assert repo.connection.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
    assert not list((blob.root / "incoming").glob(".import-*"))


def test_interrupted_copy_leaves_no_blob_or_success_record(
    tmp_path: Path, stores
) -> None:
    repo, blob = stores
    source = tmp_path / "large.txt"
    source.write_text("line of content\n" * 30000)

    def interrupted(_count: int) -> None:
        raise OSError("injected disk I/O failure")

    with pytest.raises(OSError, match="injected"):
        blob.put_file(source, on_chunk=interrupted)
    assert repo.connection.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
    assert not list((blob.root / "incoming").glob(".import-*"))
    saved = ImportSource(repo, blob).execute(source)
    assert saved.source.status is SourceStatus.STORED


def test_corrupted_private_blob_is_never_treated_as_verified(
    tmp_path: Path, stores
) -> None:
    repo, blob = stores
    source = tmp_path / "important.txt"
    source.write_text("Don't lose this")
    result = ImportSource(repo, blob).execute(source)
    blob._blob_path(result.source.content_sha256).write_text("corrupted")
    with pytest.raises(BlobError, match="SHA-256"):
        blob.verify_blob(result.source.content_sha256)
    with pytest.raises(BlobError):
        ImportSource(repo, blob).execute(source)
    assert repo.get_source(result.source.source_id).content_sha256 == result.source.content_sha256


def test_database_failure_after_fsync_allows_idempotent_recovery(
    tmp_path: Path, stores
) -> None:
    repo, blob = stores
    file = tmp_path / "hello.md"
    file.write_text("# Hello")

    class FailingRepo:
        def get_source(self, _id):
            return None

        def save_source(self, _value):
            raise OSError("simulated database is full")

    with pytest.raises(OSError, match="database"):
        ImportSource(FailingRepo(), blob).execute(file)
    assert repo.connection.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
    result = ImportSource(repo, blob).execute(file)
    assert result.source.status is SourceStatus.STORED
    assert blob.verify_blob(result.source.content_sha256) > 0


def test_source_export_is_verified_and_never_overwrites(tmp_path: Path, stores) -> None:
    repo, blob = stores
    source = tmp_path / "secret.txt"
    source.write_text("private export")
    result = ImportSource(repo, blob).execute(source)
    destination = tmp_path / "exported.txt"
    assert blob.export_original(result.source.content_sha256, destination) == len(
        source.read_bytes()
    )
    assert destination.read_bytes() == source.read_bytes()
    with pytest.raises(BlobError, match="new"):
        blob.export_original(result.source.content_sha256, destination)


def test_blob_directory_symlink_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(BlobError, match="symlink"):
        PrivateBlobStore(link)


def test_cli_import_verify_export_and_redacted_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    file = tmp_path / "unlisted-private-name.md"
    file.write_text("# Private sample")
    database = tmp_path / ".state" / "product.sqlite"
    root = tmp_path / ".state" / "source-store"
    prefix = ["--database", str(database), "--blob-root", str(root)]
    assert main([*prefix, "import", str(file)]) == 0
    printed = capsys.readouterr().out
    data = json.loads(printed)
    assert data["status"] == "stored"
    assert data["duplicate"] is False
    assert "unlisted-private-name" not in printed
    assert str(tmp_path) not in printed
    assert main([*prefix, "verify", data["source_id"]]) == 0
    assert json.loads(capsys.readouterr().out)["verified"]
    exported = tmp_path / "user-export.md"
    assert main([*prefix, "export", data["source_id"], str(exported)]) == 0
    assert json.loads(capsys.readouterr().out)["exported"]
    assert exported.read_bytes() == file.read_bytes()
    assert main([*prefix, "import", str(file)]) == 0
    assert json.loads(capsys.readouterr().out)["duplicate"] is True
