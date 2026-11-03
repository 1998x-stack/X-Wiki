"""Immutable local blob descriptor, distinct from source metadata and public Wiki."""

from dataclasses import dataclass

from .errors import ContractError
from .validation import digest


@dataclass(frozen=True, slots=True)
class BlobReceipt:
    content_sha256: str
    size_bytes: int
    media_kind: str

    def __post_init__(self) -> None:
        digest(self.content_sha256, "content_sha256")
        if type(self.size_bytes) is not int or self.size_bytes <= 0:
            raise ContractError("size_bytes must be a positive integer")
        if self.media_kind not in {"text", "audio"}:
            raise ContractError("media_kind must be text or audio")
