"""UX-002A: private, content-addressed, fsynced original-file storage.

No network, LLM, Git or public Wiki operations. A source is 'stored' only
after a complete private blob with a matching SHA-256 has been made durable.
"""

from __future__ import annotations

import codecs
import errno
import fcntl
import hashlib
import os
import stat
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from xwiki.domain.blob import BlobReceipt
from xwiki.domain.errors import ContractError
from xwiki.domain.validation import digest

CHUNK_SIZE = 128 * 1024
MAX_TEXT_BYTES = 16 * 1024 * 1024
MAX_AUDIO_BYTES = 256 * 1024 * 1024

EXTENSIONS = {
    ".txt": "text",
    ".md": "text",
    ".m4a": "audio",
    ".mp3": "audio",
    ".wav": "audio",
}


class BlobError(ContractError):
    """An input file or private blob is unsafe, damaged or unsupported."""


def _sync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        try:
            os.fsync(fd)
        except OSError as error:
            if error.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP}:
                raise
    finally:
        os.close(fd)


def _check_magic(extension: str, header: bytes) -> None:
    if extension == ".m4a" and header[4:8] != b"ftyp":
        raise BlobError("M4A input is missing an ISO base media header")
    if extension == ".wav" and not (
        header.startswith(b"RIFF") and header[8:12] == b"WAVE"
    ):
        raise BlobError("WAV input is missing a RIFF/WAVE header")
    if extension == ".mp3" and not (
        header.startswith(b"ID3")
        or (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0)
    ):
        raise BlobError("MP3 input is missing a known audio frame header")


class PrivateBlobStore:
    def __init__(self, root: Path):
        self.root = Path(root).expanduser().absolute()
        if self.root.is_symlink() or self.root.parent.is_symlink():
            raise BlobError("private blob directory cannot be a symlink")
        self.root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root.mkdir(mode=0o700, exist_ok=True)
        self.root.chmod(0o700)
        self.temp = self.root / "incoming"
        self.temp.mkdir(mode=0o700, exist_ok=True)
        if self.temp.is_symlink():
            raise BlobError("private temporary directory cannot be a symlink")

    @contextmanager
    def _lock(self) -> Iterator[None]:
        path = self.root / ".lock"
        if path.is_symlink():
            raise BlobError("blob lock cannot be a symlink")
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _blob_path(self, sha256: str) -> Path:
        digest(sha256, "blob_sha256")
        return self.root / "sha256" / sha256[:2] / (sha256 + ".blob")

    def verify_blob(self, sha256: str) -> int:
        destination = self._blob_path(sha256)
        if (
            (self.root / "sha256").is_symlink()
            or destination.parent.is_symlink()
            or destination.is_symlink()
            or not destination.is_file()
        ):
            raise BlobError("verified source blob is missing or unsafe")
        actual = hashlib.sha256()
        size = 0
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        with os.fdopen(os.open(destination, flags), "rb") as reader:
            while block := reader.read(CHUNK_SIZE):
                actual.update(block)
                size += len(block)
        if actual.hexdigest() != sha256:
            raise BlobError("private source blob failed SHA-256 verification")
        return size

    def put_file(
        self,
        path: Path,
        *,
        on_chunk: Callable[[int], None] | None = None,
    ) -> BlobReceipt:
        path = Path(path).expanduser().absolute()
        extension = path.suffix.lower()
        kind = EXTENSIONS.get(extension)
        if kind is None:
            raise BlobError("unsupported file type; use TXT, MD, M4A, MP3 or WAV")
        if path.is_symlink():
            raise BlobError("input file cannot be a symlink")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise BlobError("source must be a regular file")
            limit = MAX_TEXT_BYTES if kind == "text" else MAX_AUDIO_BYTES
            if before.st_size <= 0 or before.st_size > limit:
                raise BlobError("source is empty or exceeds the file size limit")
            header = os.read(fd, 12)
            _check_magic(extension, header)
            os.lseek(fd, 0, os.SEEK_SET)
            count = 0
            sha = hashlib.sha256()
            decoder = codecs.getincrementaldecoder("utf-8")("strict") if kind == "text" else None
            tmp_name: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb", dir=self.temp, prefix=".import-", delete=False
                ) as temporary:
                    tmp_name = Path(temporary.name)
                    os.chmod(tmp_name, 0o600)
                    with os.fdopen(os.dup(fd), "rb") as reader:
                        while chunk := reader.read(CHUNK_SIZE):
                            count += len(chunk)
                            if count > limit:
                                raise BlobError("source grew past file size limit during copy")
                            if decoder is not None:
                                try:
                                    decoder.decode(chunk, final=False)
                                except UnicodeDecodeError as error:
                                    raise BlobError("text must be UTF-8") from error
                            sha.update(chunk)
                            temporary.write(chunk)
                            if on_chunk is not None:
                                on_chunk(count)
                    if decoder is not None:
                        try:
                            decoder.decode(b"", final=True)
                        except UnicodeDecodeError as error:
                            raise BlobError("text must be UTF-8") from error
                    temporary.flush()
                    os.fsync(temporary.fileno())

                after = os.fstat(fd)
                current = path.stat()
                def relevant(value: os.stat_result) -> tuple[int, int, int, int]:
                    return value.st_ino, value.st_dev, value.st_size, value.st_mtime_ns
                if relevant(before) != relevant(after) or relevant(before) != relevant(current):
                    raise BlobError("source changed during import; retry with stable bytes")
                if count != before.st_size:
                    raise BlobError("source size changed while copying")
                sha256 = sha.hexdigest()
                destination = self._blob_path(sha256)
                with self._lock():
                    if destination.exists() or destination.is_symlink():
                        if self.verify_blob(sha256) != count:
                            raise BlobError("existing source blob size does not match")
                    else:
                        if (self.root / "sha256").is_symlink():
                            raise BlobError("unsafe hashed blob root")
                        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                        if destination.parent.is_symlink():
                            raise BlobError("unsafe blob directory")
                        os.replace(tmp_name, destination)
                        tmp_name = None
                        _sync_dir(destination.parent)
                return BlobReceipt(sha256, count, kind)
            finally:
                if tmp_name is not None:
                    tmp_name.unlink(missing_ok=True)
        finally:
            os.close(fd)

    def verified_path(self, sha256: str) -> Path:
        """Local-only verified blob path, for trusted native adapter input."""
        self.verify_blob(sha256)
        return self._blob_path(sha256)

    def is_audio(self, sha256: str) -> bool:
        """Sniff stored bytes, not a user-supplied filename or extension."""
        path = self.verified_path(sha256)
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        with os.fdopen(os.open(path, flags), "rb") as reader:
            header = reader.read(12)
        return bool(
            header[4:8] == b"ftyp"
            or (header.startswith(b"RIFF") and header[8:12] == b"WAVE")
            or header.startswith(b"ID3")
            or (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0)
        )

    def put_text(self, content: str) -> BlobReceipt:
        """Durably save derived UTF-8 transcript as a separate private blob."""
        if not isinstance(content, str) or not content.strip():
            raise BlobError("empty transcript cannot be saved")
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_TEXT_BYTES:
            raise BlobError("transcript exceeds safe text limit")
        candidate: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=self.temp, suffix=".txt", prefix=".transcript-",
                delete=False,
            ) as stream:
                candidate = Path(stream.name)
                os.chmod(candidate, 0o600)
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            return self.put_file(candidate)
        finally:
            if candidate is not None:
                candidate.unlink(missing_ok=True)

    def read_verified(self, sha256: str, *, max_bytes: int = MAX_TEXT_BYTES) -> bytes:
        size = self.verify_blob(sha256)
        if size > max_bytes:
            raise BlobError("source is too large to preview in memory")
        data = self._blob_path(sha256).read_bytes()
        if hashlib.sha256(data).hexdigest() != sha256:
            raise BlobError("source changed during read; verification failed")
        return data

    def export_original(self, sha256: str, destination: Path) -> int:
        """Copy exact bytes to an explicitly chosen new path. Never overwrite."""
        size = self.verify_blob(sha256)
        destination = Path(destination).expanduser().absolute()
        if destination.is_symlink() or destination.exists():
            raise BlobError("export destination must be a new regular file path")
        if destination.parent.is_symlink() or not destination.parent.is_dir():
            raise BlobError("export directory must already exist and not be a symlink")
        tmp: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=destination.parent, prefix=".xwiki-export-", delete=False
            ) as writer:
                tmp = Path(writer.name)
                os.chmod(tmp, 0o600)
                with self._blob_path(sha256).open("rb") as reader:
                    while block := reader.read(CHUNK_SIZE):
                        writer.write(block)
                writer.flush()
                os.fsync(writer.fileno())
            actual = hashlib.sha256()
            with tmp.open("rb") as reader:
                while chunk := reader.read(CHUNK_SIZE):
                    actual.update(chunk)
            if actual.hexdigest() != sha256:
                raise BlobError("export copy failed SHA-256 verification")
            # hard link creates atomically and fails with EEXIST on any race.
            os.link(tmp, destination)
            _sync_dir(destination.parent)
            return size
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
